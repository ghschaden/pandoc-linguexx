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
r"""What every emitter has to work out before it can write anything.

The column widths, the bands an over-wide example is broken into, and the
sizes of the number, letter and judgment columns.  All of it arithmetic over
centimetres; none of it knows what markup will carry the answer.

Split out when .docx became a second target (plan-docx.md).  A subclass adds
`example()` and whatever else its format needs; this class decides the
geometry, and two emitters over one IR is the design -- deliberately not an
abstraction over `table:table-cell` and `w:tc`, which would be a third thing
to maintain and would make both harder to read.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import ClassVar

from .inline import InlineRenderer
from .ir import Body, Example
from .latexutil import Brackets
from .measure import Grid, Plan, runs_width_cm, text_width_cm  # noqa: F401
# Grid and Plan are re-exported for the emitters: _bands returns a Plan
# and every subclass builds a Grid from what prepare() measured.
from .styles import Layout


@dataclass
class BaseEmitter:
    """Geometry shared by every target.  Subclass it to write a format."""

    layout: Layout = field(default_factory=Layout)
    inline: InlineRenderer = None  # type: ignore[assignment]
    warnings: list[str] = field(default_factory=list)

    split: bool = True
    """Break an example too wide for the text block into stacked bands."""

    brackets: Brackets = field(default_factory=Brackets)
    r"""What to wrap a number in -- \ExLBr & co., as the preamble set them."""

    any_judgment: bool = False
    """Whether *any* example in the document carries a judgment mark.

    The column is emitted for every example or for none, so the text block
    starts at the same x throughout: ../linguexx/tests/judgment-align.tex
    pins that alignment across a judged/unjudged *pair of examples*, not
    merely within one."""

    def __post_init__(self) -> None:
        if self.inline is None:
            self.inline = InlineRenderer(self.warnings.append)
        self._warn = self.warnings.append

    #: pandoc's name for the markup this emitter writes, as it appears in a
    #: RawBlock.  The inject pass tags its blocks and inlines with it.
    #:
    #: ClassVar, and it has to be: annotated plainly it becomes a dataclass
    #: FIELD, so every instance is constructed with the base class's empty
    #: default and the subclass's value never arrives.  That produced
    #: RawBlocks tagged "" and eighteen red tests.
    RAW_FORMAT: ClassVar[str] = ""

    def example(self, ex: Example) -> str:      # pragma: no cover - abstract
        raise NotImplementedError(
            f"{type(self).__name__} does not know how to emit an example")

    def reference(self, index: int, letter: str = "",
                  bare: bool = False) -> str:   # pragma: no cover - abstract
        r"""A cross-reference to example *index*, as raw markup.

        ``letter`` is a sub-example's, appended inside the brackets;
        ``bare`` drops them, which is what ``\pref`` prints.  Lives here
        rather than in the inject pass because what a reference *is* --
        a field, an anchor, a span -- is the format's business.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not know how to write a reference")

    def prepare(self, examples) -> None:
        r"""Document-level decisions, taken before the first example is emitted.

        Sizes the number, letter and judgment columns from what the document
        actually contains, so that ``(100)`` and ``viii.`` fit and a lone
        ``*`` does not reserve room for ``\%\#``.
        """
        examples = list(examples)
        lay = self.layout

        marks = [b.judgment for ex in examples for b in ex.bodies if b.judgment]
        self.any_judgment = bool(marks)
        judgment = 0.0
        if marks:
            judgment = lay.judgment_gap_cm + max(
                runs_width_cm(self.inline.runs(m), lay.em_cm, lay.sc_ratio,
                              lay.advances)
                for m in marks
            )

        wrap = self.brackets.wrap_example
        numbers = [ex.custom_label or wrap(str(ex.index + 1)) for ex in examples] \
            or [wrap("1")]
        number = max(
            runs_width_cm(self.inline.runs(n), lay.em_cm, lay.sc_ratio,
                          lay.advances)
            for n in numbers
        )
        letters = [it.marker for ex in examples for it in ex.items] or ["a."]
        letter = max(text_width_cm(m, lay.em_cm, lay.advances) for m in letters)

        self.layout = replace(
            lay,
            judgment_cm=judgment,
            number_cm=max(lay.number_cm, number + lay.pad_cm) + judgment,
            marker_cm=max(lay.marker_cm, letter + lay.pad_cm) + judgment,
        )

    # -- banding -----------------------------------------------------------
    def _bands(self, word_w: list[float], available: float, ex: Example):
        """Greedily pack words into bands no wider than the text block.

        A band is one horizontal slice of the example: its tier rows are
        emitted together, then the next band's, exactly as an overlong
        example is broken by hand.  Where the break falls is computed from
        --text-width at conversion time; reference.odt fixes the *pattern*,
        never the break points.
        """
        if not self.split:
            if sum(word_w) > available:
                self._warn(
                    f"glossed example is about {sum(word_w):.1f}cm wide against a "
                    f"{available:.1f}cm text block, and --no-split was given; "
                    f"columns were squeezed and long words will wrap in their cells"
                )
            return [(0, len(word_w))]
        bands, start, acc = [], 0, 0.0
        for j, w in enumerate(word_w):
            if acc + w > available and j > start:
                bands.append((start, j))
                start, acc = j, 0.0
            acc += w
        bands.append((start, len(word_w)))
        if len(bands) > 1:
            self._warn(
                f"glossed example does not fit the {self.layout.text_width_cm:.0f}cm "
                f"text block; split into {len(bands)} bands"
            )
        over = [j for j, w in enumerate(word_w) if w > available]
        if over:
            self._warn(
                f"{len(over)} word(s) are individually wider than the text block "
                f"and will wrap inside their cell"
            )
        return bands

    def _lead_widths(self, has_marker: bool, has_judgment: bool) -> list[float]:
        """Number, sub-example letter, judgment — in that order.

        The judgment column is **carved out of the column to its left**, not
        inserted after it.  That is what makes the mark hang: a main
        example's text still begins at ``number_cm`` and a sub-example's
        letter still sits at ``number_cm``, judgments or no judgments, so
        the letter lines up with where a main example's text starts —
        linguexx's own geometry (measured: letter and main text both at
        3.72cm, mark at 3.48cm).
        """
        lay = self.layout
        lead = [lay.number_cm]
        if has_marker:
            lead.append(lay.marker_cm)
        if has_judgment:
            lead[-1] -= lay.judgment_cm
            lead.append(lay.judgment_cm)
        return lead

    def _word_widths(self, bodies, words: int) -> list[float]:
        lay = self.layout
        widest = [0.0] * words
        for _, body in bodies:
            for tier in body.tiers:
                for i, cell in enumerate(tier.cells):
                    widest[i] = max(
                        widest[i],
                        runs_width_cm(self.inline.runs(cell), lay.em_cm,
                                      lay.sc_ratio, lay.advances),
                    )
        return [
            min(lay.max_col_cm, max(lay.min_col_cm, w * lay.width_safety + lay.pad_cm))
            for w in widest
        ]

    def plan_table(self, ex: Example) -> TablePlan:
        bodies: list[tuple[str, Body]] = (
            [("", ex.body)] if ex.body is not None else [(i.marker, i.body) for i in ex.items]
        )
        has_marker = ex.body is None
        has_judgment = self.any_judgment

        lead = self._lead_widths(has_marker, has_judgment)
        available = self.layout.text_width_cm - sum(lead)

        # \exannot puts a structural label in a column measured from the
        # LEFT edge of the text block, so labels of examples at different
        # nesting levels line up.  Reserve it, and give the body only what
        # is left before it, minus \ExAnnotSep.
        #
        # linguexx, running out of room, keeps the example full width and
        # drops the annotation to the next line.  This converter bands
        # instead -- which is what it already does to any example too wide
        # for the block, so the column stays a column at every length
        # rather than the rule changing at one.  Different from the PDF in
        # that case, and the same everywhere else.
        lay = self.layout
        has_annot = any(body.annot for _, body in bodies)
        annot_x = lay.annot_column_ratio * lay.text_width_cm
        if has_annot:
            available = max(lay.min_col_cm,
                            annot_x - sum(lead) - lay.annot_sep_em * lay.em_cm)

        # One plan per body, each measured and banded on its own words.  A
        # paradigm's items no longer pull on one another's columns; Grid
        # unions what they produce, exactly as it already did for bands.
        plans: list[Plan] = []
        for _, body in bodies:
            if body.tiers:
                word_w = self._word_widths([("", body)], body.width)
                plans.append((word_w, self._bands(word_w, available, ex)))
            else:  # unglossed: running text in one merged cell
                plans.append(([], []))
        if not any(w for w, _ in plans):  # nothing glossed: one wide column
            plans = [([available], [(0, 1)]) for _ in bodies]

        grid = Grid(plans)
        self.last_grid = grid                 # what tests measure the layout from
        columns, total = grid.columns, grid.total
        if total > available:
            # only reachable with --no-split, or when a single word is wider
            # than the whole text block: keep the declared width inside the
            # text block and let the cells wrap internally (spike S3)
            scale = available / total
            columns = [c * scale for c in columns]
            total = available
        filler = 1 if total <= available - self.layout.min_col_cm else 0
        widths = lead + columns + ([available - total] if filler else [])
        if has_annot:
            # Whatever is still unspoken for goes to the annotation, so its
            # column begins at annot_x however the body measured out.
            widths = lead + columns
            gap = annot_x - sum(lead) - total
            # Emitted however narrow it is, unlike the ordinary filler: the
            # gap IS \ExAnnotSep, and dropping it for being below
            # min_col_cm moves the annotation column an em left of where
            # every other example put it, which is the one thing a column
            # of labels may not do.
            filler = 1 if gap > 0.01 else 0
            if filler:
                widths = widths + [gap]
            widths = widths + [self.layout.text_width_cm - sum(widths)]
        return TablePlan(
            bodies=bodies, has_marker=has_marker, has_judgment=has_judgment,
            has_annot=has_annot, lead=lead, columns=columns, widths=widths,
            grid=grid, filler=filler,
        )


@dataclass
class TablePlan:
    """Where everything goes in one example's table, before any markup.

    Every field is a measurement or a count; nothing here is spelled in
    ODF or in OOXML.  The two emitters compute this the same way and then
    disagree only about how to write it down -- which is the whole point of
    the split, and the reason this is a dataclass and not a base-class
    method returning eight values.
    """

    bodies: list[tuple[str, object]]
    has_marker: bool
    has_judgment: bool
    has_annot: bool
    lead: list[float]
    columns: list[float]
    widths: list[float]
    grid: Grid
    filler: int


#: target name -> the emitter that writes it.
#:
#: One entry, and the seam is the point: plan-docx.md's Phase 1 is to put
#: it here with ODT as the only value and change nothing else, so that
#: adding "docx" later is a commit that reads as a new backend rather than
#: as a refactor with a backend buried inside it.
#:
#: Populated by the emitter modules rather than listed here, so that this
#: module keeps importing nothing that writes a format.
TARGETS: dict[str, type[BaseEmitter]] = {}


def register(name: str):
    """Class decorator: make an emitter reachable by target name."""
    def decorate(cls: type[BaseEmitter]) -> type[BaseEmitter]:
        TARGETS[name] = cls
        return cls
    return decorate


def emitter_for(target: str, **kwargs) -> BaseEmitter:
    """The emitter for *target*, constructed.

    Importing the emitters here rather than at module level: they import
    this module for BaseEmitter, and a cycle would be a poor first act for
    a seam meant to make things easier to add.
    """
    from . import emit_docx, emit_odt  # noqa: F401  (they register themselves)

    try:
        cls = TARGETS[target]
    except KeyError:
        known = ", ".join(sorted(TARGETS)) or "none"
        raise ValueError(
            f"no emitter for target {target!r}; known targets: {known}") from None
    return cls(**kwargs)
