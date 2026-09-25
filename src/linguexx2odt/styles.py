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

That rule is why the space above and below an example is a *paragraph*
style on an empty spacer row rather than the obvious ``fo:margin-top`` /
``fo:margin-bottom`` on the table.  Table margins work, but they can only
ever live in a per-example automatic style: LibreOffice ignores
``style:parent-style-name`` on ``style:family="table"``, so a named table
style in ``office:styles`` contributes nothing and never appears in the
sidebar (measured — see notes/findings.md).  A spacer row whose height is
a fixed ``fo:line-height`` on a named paragraph style reproduces the
geometry exactly and *is* editable, so that is what we emit.
"""

from __future__ import annotations

from dataclasses import dataclass

#: paragraph styles
CELL_PARA = "LxExampleCell"
TRANSLATION_PARA = "LxTranslation"
JUDGMENT_PARA = "LxJudgmentCell"
ANNOT_PARA = "LxAnnot"

#: The first row of a *continuation* band, and nothing else.
#:
#: It declares nothing and looks exactly like CELL_PARA, because that is
#: all it is for: recording where a band begins.  A finished table cannot
#: otherwise say whether three rows are three tiers of one band or one
#: tier of three bands — the rows are built alike and start at the same
#: column — and the macro's Untypeset has to know which, or it hands back
#: an example with its bands as extra gloss tiers.  Structure, not a copy
#: of anything: nothing here can drift out of step with the text.
BAND_PARA = "LxExampleBand"

#: The space around an example.  SPACE_PARA carries the height and the two
#: others inherit it unchanged, so editing the parent in the sidebar moves
#: both sides at once and editing a child moves one side only.
SPACE_PARA = "LxExampleSpace"
SPACE_ABOVE_PARA = "LxExampleSpaceAbove"
SPACE_BELOW_PARA = "LxExampleSpaceBelow"

#: table-cell automatic style
CELL = "LxExCell"

#: The number-range sequence every example number is a field of.  The Writer
#: macro writes into the same one, so a converted document and an example
#: added by hand afterwards renumber together.
SEQ_NAME = "NumEx"


# -- what the Writer macro has to agree with -------------------------------
#
# The macro is Basic and cannot import any of this, so the values live twice:
# here, and as literal Const declarations in the generated block of
# writermacro/LinguExx.bas.  tools/sync_macro.py writes that block and
# tests/test_macro_sync.py fails when the two drift apart — which they had
# already begun to do (the macro was missing max_col_cm) before this existed.

#: Basic constant name -> the string it must hold.
MACRO_NAMES: dict[str, str] = {
    "CELL_PARA": CELL_PARA,
    "TRANS_PARA": TRANSLATION_PARA,
    "JUDG_PARA": JUDGMENT_PARA,
    "BAND_PARA": BAND_PARA,
    "SPACE_PARA": SPACE_PARA,
    "SPACE_ABOVE": SPACE_ABOVE_PARA,
    "SPACE_BELOW": SPACE_BELOW_PARA,
    "SEQ_NAME": SEQ_NAME,
    "ANNOT_PARA": ANNOT_PARA,
}

#: Basic constant name -> the Layout field it must equal, in cm.
MACRO_LENGTHS: dict[str, str] = {
    "PAD_CM": "pad_cm",
    "MIN_COL_CM": "min_col_cm",
    "MAX_COL_CM": "max_col_cm",
    "NUMBER_CM": "number_cm",
    "MARKER_CM": "marker_cm",
    "JUDG_GAP_CM": "judgment_gap_cm",
    "SPACE_CM": "space_cm",
    "SC_RATIO": "sc_ratio",
    "ANNOT_RATIO": "annot_column_ratio",
    "ANNOT_SEP_EM": "annot_sep_em",
}

#: Deliberately *not* shared, with the reason — so that a value missing from
#: the macro is a decision on the record rather than an oversight.
#:
#: test_every_layout_field_is_accounted_for enforces that: a Layout field
#: belongs either to MACRO_LENGTHS or to this table.  It was added after
#: five fields had quietly reached neither, three of them for months —
#: which is the oversight this table's own comment claims to prevent, and
#: a comment cannot.
MACRO_NOT_SHARED: dict[str, str] = {
    "text_width_cm": "the macro reads the real page style instead",
    "font_pt": "the macro reads the real font instead",
    "width_safety": "the macro measures, so it needs no margin for error",
    "judgment_cm": (
        "the macro measures the mark rather than reserving a width for it; "
        "it shares JUDG_GAP_CM, which measuring cannot supply"),
    "space_above_cm": (
        "converter-only: a CLI override.  The macro carries one SPACE_CM "
        "and lets the SPACE_ABOVE/SPACE_BELOW styles hold any difference, "
        "which is what a Writer user edits"),
    "space_below_cm": "converter-only, as space_above_cm",
}

#: The same, for paragraph styles: a style the converter writes and the
#: macro knows nothing about, with what that costs.
#:
#: Empty, and worth keeping so.  It held ANNOT_PARA for one commit, with
#: the measurement that justified it: the macro read a converted
#: annotation back as a trailing word of the object tier, and re-typesetting
#: gave an eight-column grid where linguexx's is seven.  The macro now
#: knows the style, so the entry is gone rather than explained away.
MACRO_STYLES_NOT_SHARED: dict[str, str] = {}


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

    sc_ratio: float = 0.8
    """What a small capital is drawn at, as a fraction of the font size.

    Measured against rendered PDF at 12 pt Liberation Serif, not guessed:
    modelling every lowercase letter as its capital at this size reproduces
    what LibreOffice actually draws to within a few percent.  It matters
    because small caps are *wider* than the lowercase they replace — 10% to
    20% — so a \\textsc or \\lpzg column measured as lowercase is too
    narrow for what goes in it."""

    annot_column_ratio: float = 0.75
    r"""Where \exannot's column sits, as a fraction of the text block.

    linguexx's \ExAnnotColumn defaults to .75\columnwidth and is measured
    from the LEFT edge of the text block, so it does not move when the
    example is indented -- which is the whole point of it: the labels of
    examples at different nesting levels still line up.
    """

    annot_sep_em: float = 1.0
    r"""\ExAnnotSep: the least gap between an example and that column.

    An example that would come within it takes its annotation onto the
    next line instead of pushing the column right, which is what keeps the
    column a column.  linguexx's default is 1em with no stretch or shrink.
    """

    width_safety: float = 1.02
    """Multiplier on the width estimate.  Err wide: a column a little too
    generous merely looks loose, one a little too narrow breaks a word
    across two lines.

    It was 1.06 when the advance table was a four-bucket guess that already
    ran 6.7% wide on its own — so the margin was insuring against a bias in
    the same direction, and columns came out some 13% too generous.  With
    measured advances the estimate runs a median 2.9% wide (it sums
    advances and so cannot see kerning, which only ever narrows) and 1.7%
    narrow at worst over the test vocabulary, which 1.02 covers.  What is
    left insures against a body face that is not Times-metric."""

    pad_cm: float = 0.16
    """Breathing room between adjacent word columns."""

    min_col_cm: float = 0.55
    max_col_cm: float = 6.0

    space_cm: float = 0.18
    """Space above *and* below an example, unless overridden per side.

    linguexx's own \\Extopsep defaults to .66\\baselineskip; this is not
    derived from it, because nothing in the LaTeX source reaches us."""

    space_above_cm: float | None = None
    """Overrides space_cm above the example.  None means 'follow it'."""

    space_below_cm: float | None = None
    """Overrides space_cm below the example.  None means 'follow it'."""

    @property
    def em_cm(self) -> float:
        return self.font_pt / 72 * 2.54


def _space_side(name: str, override: float | None) -> str:
    """One side's spacing style.

    With no override it declares nothing of its own, so it tracks
    SPACE_PARA and a single sidebar edit there moves both sides.  Giving it
    a height of its own — from the CLI, or by editing it in Writer — breaks
    that side away without touching the other.
    """
    props = (
        f'<style:paragraph-properties fo:line-height="{override:.3f}cm"/>'
        if override is not None
        else ""
    )
    return (
        f'<style:style style:name="{name}" style:family="paragraph"'
        f' style:parent-style-name="{SPACE_PARA}">{props}</style:style>'
    )


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
            # \exannot's column.  Flush left in its own cell, which is what
            # makes a column of labels a column: linguexx sets them all at
            # \ExAnnotColumn from the text block's left edge, and the cell
            # boundary is that distance here.  \ExAnnotFont is
            # \normalfont by default, so nothing is declared about the face.
            f'<style:style style:name="{ANNOT_PARA}" style:family="paragraph"'
            f' style:parent-style-name="{CELL_PARA}">'
            f'<style:paragraph-properties fo:text-align="start"/>'
            f"</style:style>",
            # Declares nothing: it is a mark, not a look.  See BAND_PARA.
            f'<style:style style:name="{BAND_PARA}" style:family="paragraph"'
            f' style:parent-style-name="{CELL_PARA}"/>',
            # The judgment mark hangs at the right edge of its column, so it
            # sits snug against the text it judges — as linguexx \llap's it.
            f'<style:style style:name="{JUDGMENT_PARA}" style:family="paragraph"'
            f' style:parent-style-name="{CELL_PARA}">'
            f'<style:paragraph-properties fo:text-align="end"'
            f' style:justify-single-word="false"/>'
            f"</style:style>",
            # The space around an example.  A *fixed* fo:line-height is what
            # makes this exact: it clamps the empty spacer paragraph to the
            # requested height with no font-size floor, so 0cm really is 0
            # and 0.18cm really is 5.1pt (measured).  The 1pt font is only
            # belt and braces for the case where a user switches the style
            # back to single line spacing.
            f'<style:style style:name="{SPACE_PARA}" style:family="paragraph"'
            f' style:parent-style-name="{CELL_PARA}">'
            f'<style:paragraph-properties fo:line-height="{layout.space_cm:.3f}cm"/>'
            f'<style:text-properties fo:font-size="1pt"/>'
            f"</style:style>",
            _space_side(SPACE_ABOVE_PARA, layout.space_above_cm),
            _space_side(SPACE_BELOW_PARA, layout.space_below_cm),
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
