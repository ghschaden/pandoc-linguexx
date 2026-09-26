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

import functools
import subprocess

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


#: Faces that share Times metrics, so the measured table above describes
#: them and nothing has to be read off a font file.
#:
#: Not a convenience: these are what a reader actually substitutes for one
#: another.  Liberation Serif is what the table was measured from, Times New
#: Roman is what it targets, and Nimbus Roman and Tinos are the same metrics
#: again under other names.
TIMES_METRIC = frozenset({
    "times new roman", "liberation serif", "nimbus roman",
    "nimbus roman no9 l", "tinos", "thorndale amt",
})

#: What a RENDERER draws, where that differs from what the font declares.
#:
#: The built-in table was measured through LibreOffice, so it records drawn
#: widths; a font file gives the advance in the font.  They agree to 0.0022
#: em over 217 characters -- except the soft hyphen, which the font calls
#: 0.333 em and a renderer draws as nothing unless it falls at a line break.
#: Measure a font without applying this and every column holding a soft
#: hyphen comes out a third of an em too wide, which is a puzzling thing to
#: meet later.
RENDERED: dict[str, float] = {"­": 0.0}


#: Faces measured once from their font files and carried here, keyed by
#: family name without spaces, lowercased.  So a face nobody has installed
#: -- Aptos, Word's default since 2023, is not on a Linux machine and not
#: on CI -- is still estimated from its own metrics, the same numbers
#: advances_for() would read off the file.  tools/measure_face.py writes
#: this block and checks it against the font.
# --- BEGIN MEASURED FACES — see tools/measure_face.py
_FACE_ADVANCE: dict[str, dict[str, float]] = {'aptos': {' ': 0.203,
           '!': 0.293,
           '"': 0.37,
           '#': 0.537,
           '$': 0.534,
           '%': 0.826,
           '&': 0.643,
           "'": 0.21,
           '(': 0.293,
           ')': 0.293,
           '*': 0.457,
           '+': 0.534,
           ',': 0.286,
           '-': 0.34,
           '.': 0.286,
           '/': 0.339,
           '0': 0.534,
           '1': 0.534,
           '2': 0.534,
           '3': 0.534,
           '4': 0.534,
           '5': 0.534,
           '6': 0.534,
           '7': 0.534,
           '8': 0.534,
           '9': 0.534,
           ':': 0.286,
           ';': 0.286,
           '<': 0.534,
           '=': 0.534,
           '>': 0.534,
           '?': 0.501,
           '@': 0.895,
           'A': 0.589,
           'B': 0.604,
           'C': 0.692,
           'D': 0.686,
           'E': 0.556,
           'F': 0.524,
           'G': 0.708,
           'H': 0.707,
           'I': 0.26,
           'J': 0.331,
           'K': 0.568,
           'L': 0.5,
           'M': 0.79,
           'N': 0.706,
           'O': 0.732,
           'P': 0.577,
           'Q': 0.732,
           'R': 0.606,
           'S': 0.566,
           'T': 0.479,
           'U': 0.681,
           'V': 0.585,
           'W': 0.892,
           'X': 0.553,
           'Y': 0.54,
           'Z': 0.516,
           '[': 0.294,
           '\\': 0.339,
           ']': 0.294,
           '^': 0.534,
           '_': 0.46,
           '`': 0.552,
           'a': 0.531,
           'b': 0.561,
           'c': 0.525,
           'd': 0.561,
           'e': 0.527,
           'f': 0.301,
           'g': 0.484,
           'h': 0.551,
           'i': 0.239,
           'j': 0.239,
           'k': 0.487,
           'l': 0.26,
           'm': 0.853,
           'n': 0.551,
           'o': 0.552,
           'p': 0.561,
           'q': 0.561,
           'r': 0.334,
           's': 0.486,
           't': 0.323,
           'u': 0.559,
           'v': 0.452,
           'w': 0.721,
           'x': 0.442,
           'y': 0.452,
           'z': 0.438,
           '{': 0.294,
           '|': 0.27,
           '}': 0.294,
           '~': 0.534,
           '\xa0': 0.203,
           '¡': 0.287,
           '¢': 0.534,
           '£': 0.534,
           '¤': 0.534,
           '¥': 0.534,
           '¦': 0.27,
           '§': 0.47,
           '¨': 0.552,
           '©': 0.749,
           'ª': 0.429,
           '«': 0.416,
           '¬': 0.534,
           '\xad': 0.0,
           '®': 0.468,
           '¯': 0.552,
           '°': 0.365,
           '±': 0.534,
           '²': 0.34,
           '³': 0.34,
           '´': 0.552,
           'µ': 0.562,
           '¶': 0.56,
           '·': 0.286,
           '¸': 0.552,
           '¹': 0.34,
           'º': 0.447,
           '»': 0.416,
           '¼': 0.709,
           '½': 0.761,
           '¾': 0.779,
           '¿': 0.501,
           'À': 0.589,
           'Á': 0.589,
           'Â': 0.589,
           'Ã': 0.589,
           'Ä': 0.589,
           'Å': 0.589,
           'Æ': 0.933,
           'Ç': 0.692,
           'È': 0.556,
           'É': 0.556,
           'Ê': 0.556,
           'Ë': 0.556,
           'Ì': 0.26,
           'Í': 0.26,
           'Î': 0.26,
           'Ï': 0.26,
           'Ð': 0.686,
           'Ñ': 0.706,
           'Ò': 0.732,
           'Ó': 0.732,
           'Ô': 0.732,
           'Õ': 0.732,
           'Ö': 0.732,
           '×': 0.534,
           'Ø': 0.732,
           'Ù': 0.681,
           'Ú': 0.681,
           'Û': 0.681,
           'Ü': 0.681,
           'Ý': 0.54,
           'Þ': 0.577,
           'ß': 0.541,
           'à': 0.531,
           'á': 0.531,
           'â': 0.531,
           'ã': 0.531,
           'ä': 0.531,
           'å': 0.531,
           'æ': 0.845,
           'ç': 0.525,
           'è': 0.527,
           'é': 0.527,
           'ê': 0.527,
           'ë': 0.527,
           'ì': 0.239,
           'í': 0.239,
           'î': 0.239,
           'ï': 0.239,
           'ð': 0.552,
           'ñ': 0.551,
           'ò': 0.552,
           'ó': 0.552,
           'ô': 0.552,
           'õ': 0.552,
           'ö': 0.552,
           '÷': 0.534,
           'ø': 0.552,
           'ù': 0.559,
           'ú': 0.559,
           'û': 0.559,
           'ü': 0.559,
           'ý': 0.452,
           'þ': 0.561,
           'ÿ': 0.452,
           'ŋ': 0.551,
           'ɔ': 0.525,
           'ə': 0.527,
           'ɛ': 0.496,
           'ʃ': 0.255,
           'ʒ': 0.484,
           'θ': 0.549,
           '–': 0.46,
           '—': 0.92,
           '‘': 0.27,
           '’': 0.27,
           '“': 0.452,
           '”': 0.453,
           '…': 0.818,
           '′': 0.211,
           '″': 0.359}}
# --- END MEASURED FACES


class FontNotFound(Exception):
    """No file on this machine answers to that family name."""


def _font_file(name: str) -> str:
    """The file fontconfig gives for *name*, or raise.

    fontconfig always answers -- with its best match, which for a name it
    has never heard of is some default.  So the answer is checked against
    the name asked for rather than trusted, or a typo silently measures
    DejaVu Sans and the columns come out sized for it.
    """
    try:
        got = subprocess.run(
            ["fc-match", "--format=%{file}\t%{family}", name],
            capture_output=True, text=True, timeout=20, check=True).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise FontNotFound(
            f"cannot look up {name!r}: fontconfig's fc-match is not "
            f"available here ({exc})") from None
    path, _, families = got.partition("\t")
    wanted = name.lower().replace(" ", "")
    if not any(wanted == f.lower().replace(" ", "")
               for f in families.split(",")):
        raise FontNotFound(
            f"no font named {name!r} on this machine; fontconfig offered "
            f"{families.split(',')[0]!r} instead, whose metrics are not the "
            f"ones you asked for")
    return path


@functools.lru_cache(maxsize=8)
def advances_for(name: str) -> dict[str, float]:
    """Per-character advances in em for *name*, measured from the font.

    Returns the built-in table for anything Times-metric, so the common
    case reads no files at all.  Otherwise the font is measured with
    fontTools -- milliseconds, and no LibreOffice, which conversion does
    not otherwise need.

    Only the characters the built-in table covers are measured, because
    those are the ones the estimator has fallbacks tuned for; a character
    in neither is handled by _advance as it always was.
    """
    key = name.lower().replace(" ", "")
    if key in {f.replace(" ", "") for f in TIMES_METRIC}:
        return _ADVANCE
    if key in _FACE_ADVANCE:
        return _FACE_ADVANCE[key]
    return measure_font_file(_font_file(name))


def measure_font_file(path: str) -> dict[str, float]:
    """Advances in em from a font file: the characters _ADVANCE covers, each
    its hmtx advance over the units per em, rounded as the table is, with
    what a renderer draws differently (RENDERED) applied.  advances_for()
    and tools/measure_face.py both measure this way, so a committed face and
    one read off an installed file are the same numbers."""
    from fontTools.ttLib import TTFont

    font = TTFont(path, fontNumber=0, lazy=True)
    upem = font["head"].unitsPerEm
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    out: dict[str, float] = {}
    for ch in _ADVANCE:
        glyph = cmap.get(ord(ch))
        if glyph is not None:
            out[ch] = round(hmtx[glyph][0] / upem, 3)
    out.update(RENDERED)
    return out


def _advance(ch: str, advances: dict[str, float] | None = None) -> float:
    width = (advances or _ADVANCE).get(ch)
    if width is not None:
        return width
    return _FALLBACK_UPPER if ch.isupper() else _FALLBACK_OTHER


def text_width_cm(text: str, em_cm: float,
                  advances: dict[str, float] | None = None) -> float:
    """Estimated rendered width of *text*."""
    return sum(_advance(c, advances) for c in text) * em_cm


def _sc_advance(ch: str, sc_ratio: float,
                advances: dict[str, float] | None = None) -> float:
    """A small capital: the *capital's* advance, at sc_ratio of the size.

    Which is usually wider than the lowercase letter it stands in for —
    small-cap I against lowercase i is the extreme case — and occasionally
    narrower, for the letters that are already wide in lowercase.
    """
    if ch.islower():
        return _advance(ch.upper(), advances) * sc_ratio
    return _advance(ch, advances)


def runs_width_cm(runs, em_cm: float, sc_ratio: float,
                  advances: dict[str, float] | None = None) -> float:
    """Estimated width of (text, is_small_caps) runs, each measured as drawn.

    Small caps have to be measured as what they draw as, not as what they
    say: \\lpzg{3sg} sets three small capitals, and estimating them from
    "3sg" makes the column too narrow for its own contents.
    """
    return em_cm * sum(
        sum(_sc_advance(c, sc_ratio, advances) if small_caps
            else _advance(c, advances) for c in text)
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
