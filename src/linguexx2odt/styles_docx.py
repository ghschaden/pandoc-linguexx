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
r"""The Word styles an example is built from, and why there are any.

The same names the ODT target uses, so that one document opened either way
answers to the same styles and a reader learns one vocabulary.  They exist
for the reason the ODF ones do: a Word user should be able to change how
every example looks from the Styles pane, which direct formatting can never
offer.

They also settle fact 10 of plan-docx.md.  The column widths come from
`measure._ADVANCE`, which was taken from Liberation Serif at 12pt; pandoc's
default reference.docx is neither that face nor that size, so columns
computed from the table were about a third too narrow for what was drawn in
them and every longer word wrapped.  Phase 3 patched that onto every run as
direct formatting.  Declaring the face once, on the style every cell uses,
is where it belongs -- and it is also what makes it changeable, since a
user who picks another font gets columns measured for the old one and
should at least be able to see why.

A `w:pStyle` that names a style the document does not define is not an
error: the reference survives and the paragraph renders with the default
(fact 6).  So these have to be injected, and a missing injection looks like
nothing at all rather than like a failure.
"""

from __future__ import annotations

from .styles import (
    ANNOT_PARA,
    BAND_PARA,
    CELL_PARA,
    JUDGMENT_PARA,
    Layout,
    SPACE_ABOVE_PARA,
    SPACE_BELOW_PARA,
    SPACE_PARA,
    TRANSLATION_PARA,
)

#: The character style a Leipzig gloss is set in.  Its ODF counterpart is
#: created by the inline renderer; here it needs declaring like the rest.
LEIPZIG_CHAR = "LxLeipzig"

#: The face measure._ADVANCE describes.  Liberation Serif is what was
#: measured; Times New Roman is metric-compatible and is what a Word user is
#: more likely to have, so it leads and the other follows as the fallback
#: every non-Windows reader will actually find.
ESTIMATED_FONT = "Times New Roman"
FALLBACK_FONT = "Liberation Serif"


def _para(name: str, parent: str | None, props: str = "",
          run_props: str = "") -> str:
    basis = f'<w:basedOn w:val="{parent}"/>' if parent else ""
    ppr = f"<w:pPr>{props}</w:pPr>" if props else ""
    rpr = f"<w:rPr>{run_props}</w:rPr>" if run_props else ""
    return (
        f'<w:style w:type="paragraph" w:customStyle="1" w:styleId="{name}">'
        f'<w:name w:val="{name}"/>{basis}{ppr}{rpr}</w:style>'
    )


def default_font(pt: float, name: str = ESTIMATED_FONT) -> str:
    """The run properties to put on the DOCUMENT's default, not on a style.

    The columns are measured from `measure._ADVANCE`, which is Liberation
    Serif metrics, and pandoc's reference.docx names no face at all -- it
    leaves the reader to pick, and the reader picks something narrower, so
    words wrapped inside columns sized for something else.

    Phase 3 fixed that on every run and Phase 4 moved it onto the example
    style, which fixed the geometry and broke the typography: the examples
    came out in a different face from the prose around them, which the ODT
    target never does -- its LxExampleCell inherits from Standard and names
    no font.  Setting the document default instead makes the whole document
    the face the estimate describes, so the prose and the examples match
    AND the columns are right.

    Applied only when the document names no face of its own, so that a
    --reference-doc a user supplied still wins.
    """
    half = int(round(pt * 2))
    return (
        f'<w:rFonts w:ascii="{name}" w:hAnsi="{name}" '
        f'w:eastAsia="{name}" w:cs="{name}"/>'
        f'<w:sz w:val="{half}"/><w:szCs w:val="{half}"/>'
    )


def styles_fragment(layout: Layout) -> str:
    """Every style an example uses, to go inside ``<w:styles>``."""
    # No space before or after, and no first-line indent: a cell's
    # paragraph is a line of a table, not a paragraph of prose, and Word's
    # defaults give it both.
    tight = ('<w:spacing w:before="0" w:after="0" w:line="240" '
             'w:lineRule="auto"/><w:ind w:firstLine="0"/>')
    styles = [
        _para(CELL_PARA, None, tight),
        # A little air above the free translation, as in the ODT target.
        _para(TRANSLATION_PARA, CELL_PARA,
              '<w:spacing w:before="57" w:after="0"/>'),
        # The mark hangs right so it sits snug against the text it judges --
        # linguexx \llap's it.  Phase 3 did this as direct formatting on the
        # cell; it belongs on the style.
        _para(JUDGMENT_PARA, CELL_PARA, '<w:jc w:val="right"/>'),
        # Declares nothing: it is a mark, not a look.  It says "this row
        # starts a continuation band", which a finished table cannot
        # otherwise tell anyone.  Same role as in the ODT target.
        _para(BAND_PARA, CELL_PARA),
        _para(ANNOT_PARA, CELL_PARA, '<w:jc w:val="start"/>'),
        # The space around an example: an exact line height on an empty
        # spacer row, so that a user can change the gap for the whole
        # document from one style.
        _para(SPACE_PARA, CELL_PARA,
              f'<w:spacing w:before="0" w:after="0" '
              f'w:line="{int(round(layout.space_cm * 567))}" '
              f'w:lineRule="exact"/>',
              '<w:sz w:val="2"/>'),
        _para(SPACE_ABOVE_PARA, SPACE_PARA),
        _para(SPACE_BELOW_PARA, SPACE_PARA),
        f'<w:style w:type="character" w:customStyle="1" '
        f'w:styleId="{LEIPZIG_CHAR}">'
        f'<w:name w:val="{LEIPZIG_CHAR}"/>'
        f"<w:rPr><w:smallCaps/></w:rPr></w:style>",
    ]
    return "".join(styles)


def inject_styles(styles_xml: str, fragment: str) -> str:
    """Put the fragment inside ``<w:styles>``."""
    if not fragment:
        return styles_xml
    tag = "</w:styles>"
    if tag not in styles_xml:
        raise ValueError("word/styles.xml has no <w:styles> element")
    return styles_xml.replace(tag, fragment + tag, 1)
