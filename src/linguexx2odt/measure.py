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
"""How wide a thing is, and which column it lands in.

Arithmetic over centimetres, and nothing about any file format.  Split out
of emit_odt.py when .docx became a second target (plan-docx.md): band
packing and width estimation are the same calculation whether the answer is
carried by `table:table-cell` or by `w:tc`, and the ODT emitter had them
only because it was the only emitter.

Nothing here imports a writer, and nothing here should.
"""

from __future__ import annotations

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
