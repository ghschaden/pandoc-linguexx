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
from .ir import Body, Example, Item
from .styles import (
    CELL, CELL_PARA, JUDGMENT_PARA, Layout, TRANSLATION_PARA, cell_style,
)

SEQ_NAME = "NumEx"


def ref_name(index: int) -> str:
    return f"refNumEx{index}"


def sequence_field(index: int) -> str:
    """A live number-range field.  The cached value is a placeholder —
    S2 proved LibreOffice recomputes it from the formula on load."""
    return (
        f'<text:sequence text:ref-name="{ref_name(index)}" text:name="{SEQ_NAME}"'
        f' text:formula="ooow:{SEQ_NAME}+1" style:num-format="1">{index + 1}</text:sequence>'
    )


def sequence_ref(index: int, letter: str = "") -> str:
    """``(3)`` or ``(3a)`` — field plus literal letter, per the reference."""
    return (
        f'(<text:sequence-ref text:reference-format="value"'
        f' text:ref-name="{ref_name(index)}">{index + 1}</text:sequence-ref>'
        f"{esc(letter)})"
    )


#: Rough Times-like advance widths, in em.  Not real metrics — just far
#: better than counting characters, which made "AAA" narrower than "aaa".
_WIDE = "MWmw%@"
_NARROW = "iljtfr.,;:!'`|()[]{}-"


def _advance(ch: str) -> float:
    if ch in _WIDE:
        return 0.90
    if ch in _NARROW:
        return 0.32
    if ch == " ":
        return 0.25
    if ch.isupper():
        return 0.70
    if ch.isdigit():
        return 0.50
    return 0.50


def text_width_cm(text: str, em_cm: float) -> float:
    """Estimated rendered width of *text*."""
    return sum(_advance(c) for c in text) * em_cm


class Grid:
    """The shared column grid of one example's table.

    Bands each start at the left edge, so their word boundaries fall at
    different places.  A single table has one column grid, so the grid is
    the **union** of every band's boundaries and each word spans the
    columns it covers — which is precisely the structure that hand-merging
    cells in Writer produces (reference.odt item 4 reaches 22 columns for a
    13-word band over a 9-word band).
    """

    TOL = 0.015  # cm; boundaries closer than this are the same boundary

    def __init__(self, word_widths: list[float], bands: list[tuple[int, int]]) -> None:
        self.word_widths = word_widths
        self.bands = bands

        edges: list[float] = []
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
        self.columns = [
            b - a for a, b in zip([0.0] + merged, merged)
        ] or [sum(word_widths)]
        self.total = merged[-1] if merged else sum(word_widths)

        # word index -> (first grid column, span)
        self._placement: dict[int, tuple[int, int]] = {}
        for start, stop in bands:
            x = 0.0
            for j in range(start, stop):
                lo = self._edge_index(x)
                x += word_widths[j]
                hi = self._edge_index(x)
                self._placement[j] = (lo, max(1, hi - lo))

    def _edge_index(self, x: float) -> int:
        """Number of grid columns lying left of position *x*."""
        for i, e in enumerate(self.edges):
            if abs(e - x) <= self.TOL:
                return i + 1
        return sum(1 for e in self.edges if e < x)

    def span(self, word: int) -> int:
        return self._placement[word][1]


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
        """Document-level decisions, taken before the first example is emitted.

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
                text_width_cm(self.inline.plain(m), lay.em_cm) for m in marks
            )

        numbers = [ex.custom_label or f"({ex.index + 1})" for ex in examples] or ["(1)"]
        number = max(text_width_cm(self.inline.plain(n), lay.em_cm) for n in numbers)
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
        return "(" + sequence_field(ex.index) + ")"

    # -- table mode --------------------------------------------------------
    def _table(self, ex: Example) -> str:
        bodies: list[tuple[str, Body]] = (
            [("", ex.body)] if ex.body is not None else [(i.marker, i.body) for i in ex.items]
        )
        has_marker = ex.body is None
        has_judgment = self.any_judgment
        words = max((b.width for _, b in bodies), default=1) or 1

        lead = self._lead_widths(has_marker, has_judgment)
        available = self.layout.text_width_cm - sum(lead)

        if any(b.tiers for _, b in bodies):
            word_w = self._word_widths(bodies, words)
            bands = self._bands(word_w, available, ex)
        else:  # nothing glossed: one wide text column
            word_w, bands = [available], [(0, 1)]

        grid = Grid(word_w, bands)
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
        self.auto_styles.append(self._table_styles(ex.index, widths))

        cols = "".join(
            f'<table:table-column table:style-name="{_col_name(ex.index, i)}"/>'
            for i in range(len(widths))
        )

        rows: list[str] = []
        first = True
        for marker, body in bodies:
            rows += self._body_rows(ex, marker, body, first, grid, filler,
                                    has_marker, has_judgment)
            first = False

        return (
            f'<table:table table:name="LxEx{ex.index}"'
            f' table:style-name="LxExTable{ex.index}">{cols}'
            + "".join(rows)
            + "</table:table>"
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
                        widest[i], text_width_cm(self.inline.plain(cell), lay.em_cm)
                    )
        return [
            min(lay.max_col_cm, max(lay.min_col_cm, w * lay.width_safety + lay.pad_cm))
            for w in widest
        ]

    # -- rows --------------------------------------------------------------
    def _body_rows(self, ex, marker, body, first, grid, filler,
                   has_marker, has_judgment) -> list[str]:
        rows: list[str] = []
        head_used = False

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
            for band in grid.bands:
                if band[0] >= body.width:
                    continue  # this body has no words this far right
                for tier in body.tiers:
                    rows.append(
                        "<table:table-row>" + lead_cells(not head_used)
                        + self._band_cells(tier.cells, band, grid, filler)
                        + "</table:table-row>"
                    )
                    head_used = True
        else:
            rows.append(
                "<table:table-row>" + lead_cells(True)
                + self._cell(self._body_text_only(body), span=len(grid.columns) + filler)
                + "</table:table-row>"
            )
            head_used = True

        trailer = self._trailer(body)
        if trailer:
            rows.append(
                "<table:table-row>" + lead_cells(False)
                + self._cell(trailer, span=len(grid.columns) + filler,
                             style=TRANSLATION_PARA)
                + "</table:table-row>"
            )
        return rows

    def _band_cells(self, cells, band, grid, filler: int) -> str:
        """One tier's cells for one band, each spanning the grid columns it
        covers, then empty cells padding the row to the full grid width."""
        start, stop = band
        out, covered = [], 0
        for j in range(start, stop):
            span = grid.span(j)
            content = self.inline.render(cells[j]) if j < len(cells) else ""
            out.append(self._cell(content, span=span))
            covered += span
        out += [self._cell("")] * (len(grid.columns) + filler - covered)
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
            f'<style:table-properties style:width="{total:.3f}cm"'
            f' style:rel-width="100%" table:align="margins"'
            f' fo:margin-top="0.18cm" fo:margin-bottom="0.18cm"/></style:style>'
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
