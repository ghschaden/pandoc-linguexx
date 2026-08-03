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

"""Named styles injected into ``styles.xml``, and every layout constant.

Everything the converter applies is a *named* style, never one-off direct
formatting, so a LibreOffice user can restyle every example in the
document from the sidebar — the whole point of converting to ODT rather
than to a picture of a PDF.
"""

from __future__ import annotations

from dataclasses import dataclass

#: paragraph styles
CELL_PARA = "LxExampleCell"
TRANSLATION_PARA = "LxTranslation"
JUDGMENT_PARA = "LxJudgmentCell"

#: table-cell automatic style
CELL = "LxExCell"


@dataclass(frozen=True)
class Layout:
    """Every width in the emitted document derives from these."""

    text_width_cm: float = 17.0
    """A4 with 2 cm margins — the geometry of tests/reference/reference.odt."""

    number_cm: float = 1.1
    """The ``(12)`` column.  Widened by the emitter past two digits."""

    marker_cm: float = 0.7
    """The ``a.`` / ``i.`` column, present only for sub-example paradigms."""

    judgment_cm: float = 0.45
    """The ``*`` column, recomputed in Emitter.prepare from the widest mark
    actually used.  Emitted for every example in a document or for none, so
    a judged and an unjudged example start at the same x.  It is *carved
    out of* the column to its left rather than inserted, so its presence
    never shifts the text — see Emitter._lead_widths."""

    judgment_gap_cm: float = 0.12
    """Space between a judgment mark and the text it judges."""

    font_pt: float = 12.0
    """Body font size assumed when estimating column widths."""

    width_safety: float = 1.06
    """Multiplier on the width estimate.  Real font metrics are not
    available to us, so err wide: a column a little too generous merely
    looks loose, one a little too narrow breaks a word across two lines."""

    pad_cm: float = 0.16
    """Breathing room between adjacent word columns."""

    min_col_cm: float = 0.55
    max_col_cm: float = 6.0

    @property
    def em_cm(self) -> float:
        return self.font_pt / 72 * 2.54


def named_styles(layout: Layout) -> str:
    """The fragment appended inside ``<office:styles>``."""

    def char(name: str, props: str) -> str:
        return (
            f'<style:style style:name="{name}" style:family="text">'
            f"<style:text-properties {props}/></style:style>"
        )

    return "".join(
        [
            # Cells carry no spacing of their own: the gloss rows must sit
            # directly under one another, and the table style supplies the
            # space between examples.
            f'<style:style style:name="{CELL_PARA}" style:family="paragraph"'
            f' style:parent-style-name="Standard">'
            f'<style:paragraph-properties fo:margin-top="0cm"'
            f' fo:margin-bottom="0cm" fo:text-indent="0cm"/>'
            f"</style:style>",
            f'<style:style style:name="{TRANSLATION_PARA}" style:family="paragraph"'
            f' style:parent-style-name="{CELL_PARA}">'
            f'<style:paragraph-properties fo:margin-top="0.1cm"/>'
            f"</style:style>",
            # The judgment mark hangs at the right edge of its column, so it
            # sits snug against the text it judges — as linguexx \llap's it.
            f'<style:style style:name="{JUDGMENT_PARA}" style:family="paragraph"'
            f' style:parent-style-name="{CELL_PARA}">'
            f'<style:paragraph-properties fo:text-align="end"'
            f' style:justify-single-word="false"/>'
            f"</style:style>",
            char("LxLeipzig", 'fo:font-variant="small-caps"'),
            char("LxItalic", 'fo:font-style="italic"'),
            char("LxBold", 'fo:font-weight="bold"'),
            char("LxSmallCaps", 'fo:font-variant="small-caps"'),
            char("LxJudgment", 'fo:font-style="normal"'),
        ]
    )


def cell_style() -> str:
    """Borderless, padding-free cells — as in the reference document, so a
    glossed example reads as aligned text rather than as a spreadsheet."""
    return (
        f'<style:style style:name="{CELL}" style:family="table-cell">'
        f'<style:table-cell-properties fo:padding="0cm" fo:border="none"/>'
        f"</style:style>"
    )
