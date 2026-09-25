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

from dataclasses import dataclass, field, replace

from .inline import InlineRenderer, esc
from .latexutil import Brackets
from .ir import Body, Example, Item
from .styles import (
    ANNOT_PARA, BAND_PARA, CELL, CELL_PARA, JUDGMENT_PARA, Layout, SEQ_NAME,
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


def sequence_ref(index: int, letter: str = "", brackets: "Brackets | None" = None,
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


#: Advance widths in em, measured from Liberation Serif — metric-compatible
#: with Times New Roman, which is the face this estimate targets.  Check or
#: reprint them with ``python3 tools/measure_advances.py``.
#:
#: These replace a four-bucket guess (wide 0.90 / narrow 0.32 / caps 0.70 /
#: the rest 0.50) that was 8.3% out on average and, worse, 6.7% out in one
#: direction: it overestimated nearly everything, with 'I' 113% too wide and
#: 'J' 79%.  Both are common in Leipzig glosses — INF, IND, INS — so gloss
#: columns were the worst affected, and width_safety was multiplying on top
#: of a bias it was supposed to be insuring against.
# --- BEGIN MEASURED — see tools/measure_advances.py
_ADVANCE: dict[str, float] = {
    ' ': 0.251, '!': 0.334, '"': 0.409, '#': 0.502, '$': 0.502,
    '%': 0.832, '&': 0.78, "'": 0.18, '(': 0.334, ')': 0.334, '*': 0.502,
    '+': 0.566, ',': 0.251, '-': 0.334, '.': 0.251, '/': 0.277,
    '0': 0.502, '1': 0.502, '2': 0.502, '3': 0.502, '4': 0.502,
    '5': 0.502, '6': 0.502, '7': 0.502, '8': 0.502, '9': 0.502,
    ':': 0.277, ';': 0.277, '<': 0.566, '=': 0.566, '>': 0.566,
    '?': 0.446, '@': 0.922, 'A': 0.724, 'B': 0.667, 'C': 0.667,
    'D': 0.724, 'E': 0.611, 'F': 0.555, 'G': 0.724, 'H': 0.724,
    'I': 0.334, 'J': 0.39, 'K': 0.724, 'L': 0.611, 'M': 0.889, 'N': 0.724,
    'O': 0.724, 'P': 0.555, 'Q': 0.724, 'R': 0.667, 'S': 0.555,
    'T': 0.611, 'U': 0.724, 'V': 0.724, 'W': 0.945, 'X': 0.724,
    'Y': 0.724, 'Z': 0.611, '[': 0.334, '\\': 0.277, ']': 0.334,
    '^': 0.469, '_': 0.502, '`': 0.334, 'a': 0.446, 'b': 0.502,
    'c': 0.446, 'd': 0.502, 'e': 0.446, 'f': 0.334, 'g': 0.502,
    'h': 0.502, 'i': 0.277, 'j': 0.277, 'k': 0.502, 'l': 0.277, 'm': 0.78,
    'n': 0.502, 'o': 0.502, 'p': 0.502, 'q': 0.502, 'r': 0.334, 's': 0.39,
    't': 0.277, 'u': 0.502, 'v': 0.502, 'w': 0.724, 'x': 0.502,
    'y': 0.502, 'z': 0.446, '{': 0.48, '|': 0.199, '}': 0.48, '~': 0.54,
    '\xa0': 0.251, '¡': 0.334, '¢': 0.502, '£': 0.502, '¤': 0.502,
    '¥': 0.502, '¦': 0.199, '§': 0.502, '¨': 0.334, '©': 0.761,
    'ª': 0.277, '«': 0.502, '¬': 0.566, '\xad': 0.0, '®': 0.761,
    '¯': 0.502, '°': 0.401, '±': 0.551, '²': 0.3, '³': 0.3, '´': 0.334,
    'µ': 0.577, '¶': 0.454, '·': 0.334, '¸': 0.334, '¹': 0.3, 'º': 0.311,
    '»': 0.502, '¼': 0.75, '½': 0.75, '¾': 0.75, '¿': 0.446, 'À': 0.724,
    'Á': 0.724, 'Â': 0.724, 'Ã': 0.724, 'Ä': 0.724, 'Å': 0.724,
    'Æ': 0.889, 'Ç': 0.667, 'È': 0.611, 'É': 0.611, 'Ê': 0.611,
    'Ë': 0.611, 'Ì': 0.334, 'Í': 0.334, 'Î': 0.334, 'Ï': 0.334,
    'Ð': 0.724, 'Ñ': 0.724, 'Ò': 0.724, 'Ó': 0.724, 'Ô': 0.724,
    'Õ': 0.724, 'Ö': 0.724, '×': 0.566, 'Ø': 0.724, 'Ù': 0.724,
    'Ú': 0.724, 'Û': 0.724, 'Ü': 0.724, 'Ý': 0.724, 'Þ': 0.555,
    'ß': 0.502, 'à': 0.446, 'á': 0.446, 'â': 0.446, 'ã': 0.446,
    'ä': 0.446, 'å': 0.446, 'æ': 0.667, 'ç': 0.446, 'è': 0.446,
    'é': 0.446, 'ê': 0.446, 'ë': 0.446, 'ì': 0.277, 'í': 0.277,
    'î': 0.277, 'ï': 0.277, 'ð': 0.502, 'ñ': 0.502, 'ò': 0.502,
    'ó': 0.502, 'ô': 0.502, 'õ': 0.502, 'ö': 0.502, '÷': 0.551,
    'ø': 0.502, 'ù': 0.502, 'ú': 0.502, 'û': 0.502, 'ü': 0.502,
    'ý': 0.502, 'þ': 0.502, 'ÿ': 0.502, 'ŋ': 0.495, 'ɑ': 0.525,
    'ɔ': 0.446, 'ə': 0.446, 'ɛ': 0.42, 'ɜ': 0.42, 'ɡ': 0.502, 'ɪ': 0.277,
    'ʃ': 0.334, 'ʊ': 0.551, 'ʌ': 0.502, 'ʒ': 0.446, 'ˈ': 0.334,
    'ˌ': 0.334, 'ː': 0.277, 'θ': 0.48, '‐': 0.334, '–': 0.502, '—': 1.001,
    '‘': 0.334, '’': 0.334, '“': 0.446, '”': 0.446, '…': 1.001,
    '′': 0.217, '″': 0.416,
}
# --- END MEASURED

#: For anything the table does not cover.  Deliberately unambitious: Latin
#: text is covered, and a script that is not (CJK, rarer IPA) is not going
#: to be served by a single number anyway.
_FALLBACK_UPPER = 0.667
_FALLBACK_OTHER = 0.5


def _advance(ch: str) -> float:
    width = _ADVANCE.get(ch)
    if width is not None:
        return width
    return _FALLBACK_UPPER if ch.isupper() else _FALLBACK_OTHER


def text_width_cm(text: str, em_cm: float) -> float:
    """Estimated rendered width of *text*."""
    return sum(_advance(c) for c in text) * em_cm


def _sc_advance(ch: str, sc_ratio: float) -> float:
    """A small capital: the *capital's* advance, at sc_ratio of the size.

    Which is usually wider than the lowercase letter it stands in for —
    small-cap I against lowercase i is the extreme case — and occasionally
    narrower, for the letters that are already wide in lowercase.
    """
    if ch.islower():
        return _advance(ch.upper()) * sc_ratio
    return _advance(ch)


def runs_width_cm(runs, em_cm: float, sc_ratio: float) -> float:
    """Estimated width of (text, is_small_caps) runs, each measured as drawn.

    Small caps have to be measured as what they draw as, not as what they
    say: \\lpzg{3sg} sets three small capitals, and estimating them from
    "3sg" makes the column too narrow for its own contents.
    """
    return em_cm * sum(
        sum(_sc_advance(c, sc_ratio) if small_caps else _advance(c) for c in text)
        for text, small_caps in runs
    )


#: one body's own layout: its word widths, and the bands they were packed
#: into.  An unglossed body has neither.
Plan = tuple[list[float], list[tuple[int, int]]]


class Grid:
    """The column grid of one example's table.

    Two things start at the left edge and so put their word boundaries in
    different places: the **bands** an overlong body is broken into, and
    the separate **bodies** of a sub-example paradigm.  A single table has
    one column grid, so the grid is the **union** of every boundary either
    produces, and each word spans the columns it covers — precisely the
    structure that hand-merging cells in Writer produces (reference.odt
    item 4 reaches 22 columns for a 13-word band over a 9-word band).

    Sharing one *width per word index* across bodies instead — which is
    what this did until the union was widened to cover them — couples the
    items together: item a's second column has to be as wide as item b's
    second column, so a three-word sentence acquires a gap in the middle
    because a longer word sits under it in an unrelated sentence.  Bands
    were already exempt from that coupling; items are now too.
    """

    TOL = 0.015  # cm; boundaries closer than this are the same boundary

    def __init__(self, plans: list[Plan]) -> None:
        self.plans = plans

        edges: list[float] = []
        for word_widths, bands in plans:
            for start, stop in bands:
                x = 0.0
                for j in range(start, stop):
                    x += word_widths[j]
                    edges.append(x)
        merged: list[float] = []
        for x in sorted(edges):
            if not merged or x - merged[-1] > self.TOL:
                merged.append(x)
        self.edges = merged
        widest = max((sum(w) for w, _ in plans), default=0.0)
        self.columns = [
            b - a for a, b in zip([0.0] + merged, merged)
        ] or [widest]
        self.total = merged[-1] if merged else widest

        # (body index, word index) -> (first grid column, span)
        self._placement: dict[tuple[int, int], tuple[int, int]] = {}
        for k, (word_widths, bands) in enumerate(plans):
            for start, stop in bands:
                x = 0.0
                for j in range(start, stop):
                    lo = self._edge_index(x)
                    x += word_widths[j]
                    hi = self._edge_index(x)
                    self._placement[(k, j)] = (lo, max(1, hi - lo))

    def _edge_index(self, x: float) -> int:
        """Number of grid columns lying left of position *x*."""
        for i, e in enumerate(self.edges):
            if abs(e - x) <= self.TOL:
                return i + 1
        return sum(1 for e in self.edges if e < x)

    def bands_of(self, body: int) -> list[tuple[int, int]]:
        return self.plans[body][1]

    def span(self, body: int, word: int) -> int:
        return self._placement[(body, word)][1]


def _col_name(ex_index: int, col: int) -> str:
    return f"LxExCol{ex_index}.{col}"


@dataclass
class Emitter:
    layout: Layout = field(default_factory=Layout)
    inline: InlineRenderer = None  # type: ignore[assignment]
    warnings: list[str] = field(default_factory=list)
    auto_styles: list[str] = field(default_factory=list)

    split: bool = True
    """Break an example too wide for the text block into stacked bands."""

    brackets: Brackets = field(default_factory=Brackets)
    """What to wrap a number in -- \\ExLBr & co., as the preamble set them."""

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
                runs_width_cm(self.inline.runs(m), lay.em_cm, lay.sc_ratio)
                for m in marks
            )

        wrap = self.brackets.wrap_example
        numbers = [ex.custom_label or wrap(str(ex.index + 1)) for ex in examples] \
            or [wrap("1")]
        number = max(
            runs_width_cm(self.inline.runs(n), lay.em_cm, lay.sc_ratio)
            for n in numbers
        )
        letters = [it.marker for ex in examples for it in ex.items] or ["a."]
        letter = max(text_width_cm(m, lay.em_cm) for m in letters)

        self.layout = replace(
            lay,
            judgment_cm=judgment,
            number_cm=max(lay.number_cm, number + lay.pad_cm) + judgment,
            marker_cm=max(lay.marker_cm, letter + lay.pad_cm) + judgment,
        )

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
                                      lay.sc_ratio),
                    )
        return [
            min(lay.max_col_cm, max(lay.min_col_cm, w * lay.width_safety + lay.pad_cm))
            for w in widest
        ]

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
