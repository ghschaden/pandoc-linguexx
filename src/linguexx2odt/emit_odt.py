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

"""Stage 2 — IR -> one opaque ``opendocument`` block per example.

Every example becomes one borderless *table*, as plan.md specified.
Paragraphs with tab stops — which is how the reference document renders
its unglossed examples — were implemented first and then abandoned: ODF
measures ``style:tab-stop`` positions from the paragraph's own indent, so
no tab stop can address the outdented region where the number and the
sub-example letter sit.  That makes it impossible to hang a judgment mark
without shifting the text block, which is exactly the invariant
``../linguexx/tests/judgment-align.tex`` pins.  See notes/findings.md.

Numbers are live ``text:sequence`` fields named NumEx; the parentheses
around them are literal text, exactly as a Writer user would type them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from .emit_base import BaseEmitter, register
from .inline import esc
from .latexutil import Brackets
from .ir import Body, Example
from .styles import (
    ANNOT_PARA, BAND_PARA, CELL, CELL_PARA, JUDGMENT_PARA, SEQ_NAME,
    SPACE_ABOVE_PARA, SPACE_BELOW_PARA, TRANSLATION_PARA, cell_style,
)


def ref_name(index: int) -> str:
    return f"refNumEx{index}"


def sequence_field(index: int) -> str:
    """A live number-range field.  The cached value is a placeholder —
    S2 proved LibreOffice recomputes it from the formula on load."""
    return (
        f'<text:sequence text:ref-name="{ref_name(index)}" text:name="{SEQ_NAME}"'
        f' text:formula="ooow:{SEQ_NAME}+1" style:num-format="1">{index + 1}</text:sequence>'
    )


def sequence_ref(index: int, letter: str = "", brackets: Brackets | None = None,
                 bare: bool = False) -> str:
    """``(3)`` or ``(3a)`` — field plus literal letter, per the reference.

    The brackets are the document's (``\\ExLBr``/``\\ExRBr``), not always
    parentheses.  ``bare`` drops them, which is what ``\\pref`` prints; it
    used to be done by slicing a character off each end of the finished
    XML, which is right only while they are one character each.
    """
    br = brackets or Brackets()
    left, right = ("", "") if bare else (esc(br.ex_l), esc(br.ex_r))
    return (
        f'{left}<text:sequence-ref text:reference-format="value"'
        f' text:ref-name="{ref_name(index)}">{index + 1}</text:sequence-ref>'
        f"{esc(letter)}{right}"
    )






def _col_name(ex_index: int, col: int) -> str:
    return f"LxExCol{ex_index}.{col}"


@register("odt")
@dataclass
class Emitter(BaseEmitter):
    """OpenDocument.  The geometry is BaseEmitter's; this writes the XML."""

    RAW_FORMAT: ClassVar[str] = "opendocument"

    auto_styles: list[str] = field(default_factory=list)
    """Automatic column styles, which a raw block cannot carry itself and
    postprocess injects into content.xml.  ODF-only: OOXML puts a column's
    width inline in the cell."""


    def reference(self, index: int, letter: str = "",
                  bare: bool = False) -> str:
        return sequence_ref(index, letter, self.brackets, bare=bare)

    # -- entry point ------------------------------------------------------
    def example(self, ex: Example) -> str:
        def warn(msg: str) -> None:
            self.warnings.append(f"line {ex.line}: {msg}")

        self._warn = warn
        return self._table(ex)

    def styles_fragment(self) -> str:
        """Automatic styles the emitted blocks reference; postprocess.py
        splices this into ``content.xml``'s automatic-styles section."""
        return (
            cell_style()
            + "".join(self.auto_styles)
            + "".join(self.inline.fallback_styles)
        )

    def _text(self, body: Body) -> str:
        parts = [self.inline.render(body.text)]
        if body.translation:
            parts.append(self._translation(body))
        if body.source:
            parts.append(" " + self.inline.render(body.source))
        return " ".join(p for p in parts if p)

    def _translation(self, body: Body) -> str:
        return self.inline.render(body.translation)

    def _judgment(self, body: Body) -> str:
        if not body.judgment:
            return ""
        return (
            '<text:span text:style-name="LxJudgment">'
            + self.inline.render(body.judgment)
            + "</text:span>"
        )

    def _number_text(self, ex: Example) -> str:
        if ex.custom_label:
            return self.inline.render(ex.custom_label)
        br = self.brackets
        return esc(br.ex_l) + sequence_field(ex.index) + esc(br.ex_r)

    # -- table mode --------------------------------------------------------
    def _table(self, ex: Example) -> str:
        """Render the shared plan as ODF.

        The arithmetic -- lead columns, bands, the \\exannot column, the
        filler -- is BaseEmitter.plan_table(); what is left here is the
        markup, which is the only thing the two targets do not share.
        """
        p = self.plan_table(ex)
        bodies, grid, filler = p.bodies, p.grid, p.filler
        has_marker, has_judgment, has_annot = (
            p.has_marker, p.has_judgment, p.has_annot)
        widths = p.widths
        self.auto_styles.append(self._table_styles(ex.index, widths))

        cols = "".join(
            f'<table:table-column table:style-name="{_col_name(ex.index, i)}"/>'
            for i in range(len(widths))
        )

        rows: list[str] = []
        for k, (marker, body) in enumerate(bodies):
            rows += self._body_rows(ex, marker, body, k == 0, grid, k, filler,
                                    has_marker, has_judgment, has_annot)

        span = len(widths)
        rows = (
            [self._spacer_row(SPACE_ABOVE_PARA, span)]
            + rows
            + [self._spacer_row(SPACE_BELOW_PARA, span)]
        )

        return (
            f'<table:table table:name="LxEx{ex.index}"'
            f' table:style-name="LxExTable{ex.index}">{cols}'
            + "".join(rows)
            + "</table:table>"
        )

    def _spacer_row(self, style: str, span: int) -> str:
        """An empty full-width row whose only job is to be *style*'s height.

        This is where the space above and below an example lives, so that a
        Writer user can change it for the whole document from the Styles
        sidebar — which a table margin can never offer.  See styles.py."""
        return "<table:table-row>" + self._cell("", span=span, style=style) + "</table:table-row>"




    # -- rows --------------------------------------------------------------
    def _body_rows(self, ex, marker, body, first, grid, body_index, filler,
                   has_marker, has_judgment, has_annot=False) -> list[str]:
        rows: list[str] = []
        head_used = False

        def annot_cell(active: bool) -> str:
            r"""The \exannot column, on the body's first row only.

            Every row of the table carries the cell once the column exists,
            because a table row that is short by one cell is not a shorter
            row -- it is a broken one.  Only the first row of a body puts
            anything in it: linguexx sets the label level with the object
            tier, not under the free translation."""
            if not has_annot:
                return ""
            content = self.inline.render(body.annot) if (active and body.annot) else ""
            return self._cell(content, style=ANNOT_PARA)

        def lead_cells(active: bool) -> str:
            """Number / marker / judgment cells.  Only the first row of a
            body carries them, and only its first band — a continuation
            band leaves them empty, as in reference.odt."""
            out = [self._cell(self._number_text(ex) if (active and first) else "")]
            if has_marker:
                out.append(self._cell(esc(marker) if active else ""))
            if has_judgment:
                out.append(
                    self._cell(
                        self._judgment(body) if active else "", style=JUDGMENT_PARA
                    )
                )
            return "".join(out)

        if body.tiers:
            for b, band in enumerate(grid.bands_of(body_index)):
                for t, tier in enumerate(body.tiers):
                    # The first row of a continuation band says so, because
                    # nothing else in the finished table can: a band's rows
                    # are built exactly like a tier's and start in the same
                    # column.  The macro's Untypeset reads this to tell one
                    # from the other.  See styles.BAND_PARA.
                    style = BAND_PARA if b and not t else CELL_PARA
                    rows.append(
                        "<table:table-row>" + lead_cells(not head_used)
                        + self._band_cells(tier.cells, band, grid, body_index,
                                           filler, style)
                        + annot_cell(not head_used)
                        + "</table:table-row>"
                    )
                    head_used = True
        else:
            rows.append(
                "<table:table-row>" + lead_cells(True)
                + self._cell(self._body_text_only(body), span=len(grid.columns) + filler)
                + annot_cell(True)
                + "</table:table-row>"
            )
            head_used = True

        trailer = self._trailer(body)
        if trailer:
            rows.append(
                "<table:table-row>" + lead_cells(False)
                + self._cell(trailer, span=len(grid.columns) + filler,
                             style=TRANSLATION_PARA)
                + annot_cell(False)
                + "</table:table-row>"
            )
        return rows

    def _band_cells(self, cells, band, grid, body_index: int, filler: int,
                    style: str = CELL_PARA) -> str:
        """One tier's cells for one band, each spanning the grid columns it
        covers, then empty cells padding the row to the full grid width.

        *style* marks the whole row, padding included, so a reader can find
        the mark on any cell of it rather than having to know which cells a
        short tier left empty."""
        start, stop = band
        out, covered = [], 0
        for j in range(start, stop):
            span = grid.span(body_index, j)
            content = self.inline.render(cells[j]) if j < len(cells) else ""
            out.append(self._cell(content, span=span, style=style))
            covered += span
        out += [self._cell("", style=style)] * (
            len(grid.columns) + filler - covered)
        return "".join(out)

    def _body_text_only(self, body: Body) -> str:
        parts = [self.inline.render(body.text)]
        if body.source:
            parts.append(self.inline.render(body.source))
        return " ".join(p for p in parts if p)

    def _trailer(self, body: Body) -> str:
        if not body.tiers:
            return self._translation(body) if body.translation else ""
        parts = []
        if body.translation:
            parts.append(self._translation(body))
        if body.source:
            parts.append(self.inline.render(body.source))
        return " ".join(parts)

    def _cell(self, content: str, span: int = 1, style: str = CELL_PARA) -> str:
        sp = f' table:number-columns-spanned="{span}"' if span > 1 else ""
        covered = "<table:covered-table-cell/>" * (span - 1)
        return (
            f'<table:table-cell table:style-name="{CELL}"{sp} office:value-type="string">'
            f'<text:p text:style-name="{style}">{content}</text:p>'
            f"</table:table-cell>{covered}"
        )

    # -- widths ------------------------------------------------------------
    def _table_styles(self, index: int, widths: list[float]) -> str:
        total = sum(widths)
        out = [
            f'<style:style style:name="LxExTable{index}" style:family="table">'
            # No margins here: the spacer rows carry the spacing, and a
            # margin as well would add to them.  Stated rather than omitted
            # so an inherited default from a --reference-doc cannot creep in.
            f'<style:table-properties style:width="{total:.3f}cm"'
            f' style:rel-width="100%" table:align="margins"'
            f' fo:margin-top="0cm" fo:margin-bottom="0cm"/></style:style>'
        ]
        for i, w in enumerate(widths):
            rel = round(w / total * 10000)
            out.append(
                f'<style:style style:name="{_col_name(index, i)}"'
                f' style:family="table-column">'
                f'<style:table-column-properties style:column-width="{w:.3f}cm"'
                f' style:rel-column-width="{rel}*"/></style:style>'
            )
        return "".join(out)
