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

"""Unit tests for the column grid of a split (banded) example.

A single table has one column grid, so when an overlong example is broken
into bands the grid must be the *union* of every band's word boundaries,
with each word spanning the columns it covers.  That is the structure
hand-merging cells in Writer produces, and the structure item 4 of
tests/reference/reference.odt exhibits.
"""

from __future__ import annotations

import pytest

from linguexx2odt.emit_odt import Emitter, Grid, text_width_cm
from linguexx2odt.extract import parse
from linguexx2odt.styles import (
    BAND_PARA, SPACE_ABOVE_PARA, SPACE_BELOW_PARA, TRANSLATION_PARA, Layout,
)


def positions(grid: Grid, body: int = 0) -> dict[int, float]:
    """Left edge of each word of *body*, derived only from the emitted grid."""
    starts = {}
    edges = [0.0] + grid.edges
    for band in grid.bands_of(body):
        col = 0
        for j in range(*band):
            starts[j] = edges[col]
            col += grid.span(body, j)
    return starts


def test_single_band_grid_is_just_the_words() -> None:
    w = [1.0, 2.0, 1.5]
    grid = Grid([(w, [(0, 3)])])
    assert grid.columns == pytest.approx(w)
    assert [grid.span(0, j) for j in range(3)] == [1, 1, 1]
    assert grid.total == pytest.approx(4.5)


def test_two_bands_share_a_union_grid() -> None:
    """Band A: 1.0 | 2.0 | 1.0   (edges 1.0, 3.0, 4.0)
       Band B: 1.5 | 2.5         (edges 1.5, 4.0)
       union edges: 1.0, 1.5, 3.0, 4.0  -> 4 columns"""
    w = [1.0, 2.0, 1.0, 1.5, 2.5]
    grid = Grid([(w, [(0, 3), (3, 5)])])
    assert grid.edges == pytest.approx([1.0, 1.5, 3.0, 4.0])
    assert len(grid.columns) == 4
    assert grid.total == pytest.approx(4.0)
    # every word still starts where its own band says it should
    assert positions(grid) == pytest.approx({0: 0.0, 1: 1.0, 2: 3.0, 3: 0.0, 4: 1.5})


def test_two_bodies_share_a_union_grid() -> None:
    """The same union, across the items of a paradigm rather than bands.

    Item a: 1.0 | 2.0   (edges 1.0, 3.0)
    Item b: 1.5 | 2.5   (edges 1.5, 4.0)
    union edges: 1.0, 1.5, 3.0, 4.0

    Each item keeps its *own* widths.  Sharing one width per word index
    instead is what made a three-word sentence stretch to fit a long word
    sitting under it in an unrelated one.
    """
    grid = Grid([([1.0, 2.0], [(0, 2)]), ([1.5, 2.5], [(0, 2)])])
    assert grid.edges == pytest.approx([1.0, 1.5, 3.0, 4.0])
    assert positions(grid, 0) == pytest.approx({0: 0.0, 1: 1.0})
    assert positions(grid, 1) == pytest.approx({0: 0.0, 1: 1.5})
    # neither item was widened by the other
    assert grid.total == pytest.approx(4.0)


def test_a_short_item_is_not_stretched_by_a_long_one() -> None:
    """The regression this union was widened for.

    Item a's second word must start at its own first word's width, not at
    the width of item b's much longer second word.
    """
    grid = Grid([([1.0, 1.0, 1.0], [(0, 3)]), ([1.0, 6.0], [(0, 2)])])
    assert positions(grid, 0) == pytest.approx({0: 0.0, 1: 1.0, 2: 2.0})
    assert positions(grid, 1) == pytest.approx({0: 0.0, 1: 1.0})


def test_every_band_row_covers_the_whole_grid() -> None:
    """Each table row must account for every column, or the table is
    malformed and cells drift out of their columns."""
    w = [1.0, 2.0, 1.0, 1.5, 2.5]
    grid = Grid([(w, [(0, 3), (3, 5)])])
    for band in grid.bands_of(0):
        covered = sum(grid.span(0, j) for j in range(*band))
        assert covered <= len(grid.columns)


def test_coincident_boundaries_do_not_create_slivers() -> None:
    """Bands whose words happen to break at the same x share one edge."""
    w = [1.0, 1.0, 2.0]
    grid = Grid([(w, [(0, 2), (2, 3)])])
    assert grid.edges == pytest.approx([1.0, 2.0])
    assert len(grid.columns) == 2


# -- banding decisions ------------------------------------------------------

def _emitter(**kw) -> Emitter:
    e = Emitter(layout=Layout(text_width_cm=17.0), **kw)
    e._warn = e.warnings.append
    return e


def test_short_example_is_not_split() -> None:
    e = _emitter()
    assert e._bands([1.0, 1.0, 1.0], 15.0, None) == [(0, 3)]
    assert e.warnings == []


def test_long_example_is_split_and_says_so() -> None:
    e = _emitter()
    bands = e._bands([3.0] * 10, 10.0, None)
    assert bands == [(0, 3), (3, 6), (6, 9), (9, 10)]
    assert any("split into 4 bands" in w for w in e.warnings)


def test_no_split_keeps_one_band_but_still_warns() -> None:
    e = _emitter(split=False)
    assert e._bands([3.0] * 10, 10.0, None) == [(0, 10)]
    assert any("--no-split" in w for w in e.warnings)


def test_word_wider_than_the_page_gets_its_own_band() -> None:
    e = _emitter()
    bands = e._bands([1.0, 20.0, 1.0], 10.0, None)
    assert (1, 2) in bands, "an oversized word must not be merged into a neighbour"
    assert any("wider than the text block" in w for w in e.warnings)


def test_bands_respect_the_text_width() -> None:
    e = _emitter()
    widths = [1.3, 2.2, 0.9, 3.1, 1.7, 2.8, 1.1, 2.4, 1.9, 2.6]
    for start, stop in e._bands(widths, 8.0, None):
        band = sum(widths[start:stop])
        assert band <= 8.0 or stop - start == 1


# -- the emitted table ------------------------------------------------------

LONG = r"""\begin{document}
\ex. \gll Este es un ejemplo bastante largo para llenar la linea entera y todo lo que quiero mostrar \\
     this is a example rather long to fill the line whole and all it that want show \\
\glt `A long one.'

\end{document}"""


def test_split_table_numbers_the_first_band_only() -> None:
    e = Emitter(layout=Layout(text_width_cm=17.0))
    ex = parse(LONG).examples[0]
    e.prepare([ex])
    xml = e.example(ex)
    assert xml.count("<text:sequence ") == 1, "the number belongs to the first band only"
    assert any("split into" in w for w in e.warnings)


def test_split_table_rows_all_have_the_same_column_count() -> None:
    """The invariant that makes a banded table render at all."""
    e = Emitter(layout=Layout(text_width_cm=17.0))
    ex = parse(LONG).examples[0]
    e.prepare([ex])
    xml = e.example(ex)

    ncols = xml.count("<table:table-column ")
    rows = xml.split("<table:table-row>")[1:]
    assert len(rows) >= 4, "a split example has at least two bands of two tiers"
    for n, row in enumerate(rows):
        spanned = sum(
            int(s) for s in __import__("re").findall(
                r'table:number-columns-spanned="(\d+)"', row
            )
        )
        plain = row.count("<table:table-cell ") - row.count("number-columns-spanned")
        covered = spanned + plain
        assert covered == ncols, f"row {n} covers {covered} of {ncols} columns"


UNEQUAL = r"""\begin{document}
\ex.
\a. \gll Ich habe geschlafen \\
         I have slept \\
\b. \gll Der ausserordentlich lange Beispielsatz hier \\
         the extraordinarily long example.sentence here \\
\z.

\end{document}"""


def test_a_paradigm_item_is_not_stretched_by_its_neighbour() -> None:
    """The emitter must plan each item on its own words, not on the widest.

    Word widths used to be computed once for the whole example and shared
    by every body, so item a's third column had to be as wide as item b's:
    "Ich habe geschlafen" acquired a gap in the middle because
    "ausserordentlich" sits under "habe" in an unrelated sentence.  Asserted
    on where the grid puts each item's words, which is the thing that was
    wrong — counting columns would not have caught it.
    """
    e = Emitter(layout=Layout(text_width_cm=17.0))
    ex = parse(UNEQUAL).examples[0]
    e.prepare([ex])
    e.example(ex)                      # builds and records the grid
    grid = e.last_grid

    short, wide = positions(grid, 0), positions(grid, 1)
    # each item's words sit at the sum of *its own* preceding widths
    assert short[2] == pytest.approx(sum(grid.plans[0][0][:2]))
    assert wide[2] == pytest.approx(sum(grid.plans[1][0][:2]))
    # and the short item is genuinely narrower, not merely differently spelt
    assert short[2] < wide[2] - 1.0


def test_continuation_bands_are_marked() -> None:
    """A band's first row says it is one, and a tier row does not.

    Nothing else in a finished table can tell the two apart — both are
    built the same way and start in the same column — so the macro's
    Untypeset reads this mark to know whether four rows are four tiers of
    one band or two tiers of two bands.  See styles.BAND_PARA.
    """
    e = Emitter(layout=Layout(text_width_cm=17.0))
    ex = parse(LONG).examples[0]
    e.prepare([ex])
    rows = e.example(ex).split("<table:table-row>")[1:]

    # the spacer rows top and tail it; the translation has its own row
    body = [r for r in rows
            if TRANSLATION_PARA not in r and SPACE_ABOVE_PARA not in r
            and SPACE_BELOW_PARA not in r]
    tiers = 2                                   # \gll: object and gloss
    bands = len(body) // tiers
    assert bands >= 2, "this example is meant to be a split one"

    marked = [n for n, row in enumerate(body) if BAND_PARA in row]
    assert marked == [n * tiers for n in range(1, bands)], (
        "the mark belongs on the first row of every band after the first, "
        f"got rows {marked} of {len(body)}")
    for n in marked:
        assert body[n].count(BAND_PARA) > 1, (
            "a marked row is marked across the row, so a reader finds it on "
            "whichever cell it looks at")
