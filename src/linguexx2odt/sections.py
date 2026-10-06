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
r"""The document's sections, as references to them see them.

A ``\ref`` to a section was deleted: pandoc, reading with ``raw_tex``, keeps
it as raw LaTeX, and the writer drops raw LaTeX.  It is a field now, like a
reference to an example (plan-crossrefs.md), and the field needs two things
from here: where the section is (pandoc bookmarks every heading with its
label, in both formats) and what the reference shows until a reader
recomputes it -- the number LaTeX prints.  A .docx reader may never
recompute (OnlyOffice does not), so that cached number must be right.

Format-agnostic: no markup here, as in measure and emit_base (a test holds
all three to it).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: LaTeX's article numbers \section, \subsection and \subsubsection
#: (secnumdepth 3); pandoc makes them header levels 1-3.
NUMBERED_LEVELS = 3

#: hyperref's \autoref names, by header level (\sectionautorefname & co.).
AUTOREF_NAMES = {1: "section", 2: "subsection", 3: "subsubsection",
                 4: "paragraph", 5: "subparagraph"}

#: The prefix of the bookmark the converter puts in an unnumbered heading;
#: the postprocess keeps the outline numbering off that heading by it.
UNNUMBERED = "_Reflxnon"


@dataclass(frozen=True)
class Section:
    ident: str
    """The label pandoc gave the heading: the document's \\label, or a slug."""
    level: int
    title: str
    number: str | None
    """Its own number, "1.1"; None for \\section* and below subsubsection."""
    shown: str
    r"""What \ref to it prints: its number, or for an unnumbered one the
    last number set before it, as LaTeX's \@currentlabel has it."""
    serial: int
    """Its place among the document's headings, from 0."""

    @property
    def bookmark(self) -> str:
        """A bookmark name a .docx can hold (letters, digits, underscores):
        pandoc's own is the label, "sec:intro", which Word does not accept.
        It also says whether the heading is numbered (UNNUMBERED)."""
        return f"{'_Reflxsec' if self.number else UNNUMBERED}{self.serial}"


def _text(inlines: Any) -> str:
    out: list[str] = []
    for node in inlines or []:
        if not isinstance(node, dict):
            continue
        t, c = node.get("t"), node.get("c")
        if t == "Str":
            out.append(c)
        elif t in ("Space", "SoftBreak", "LineBreak"):
            out.append(" ")
        elif t in ("Emph", "Strong", "SmallCaps", "Underline", "Strikeout",
                   "Superscript", "Subscript"):
            out.append(_text(c))
        elif t == "Quoted":
            left, right = ("\u201c", "\u201d") if c[0].get("t") == "DoubleQuote" \
                else ("\u2018", "\u2019")
            out.append(left + _text(c[1]) + right)
        elif t in ("Span", "Link", "Cite"):
            out.append(_text(c[1]))
        elif t in ("Code", "Math"):
            out.append(c[1])
    return "".join(out)


def _headers(blocks: Any):
    """Every Header, in document order, also inside a Div."""
    for b in blocks or []:
        if not isinstance(b, dict):
            continue
        if b.get("t") == "Header":
            yield b
        elif b.get("t") == "Div":
            yield from _headers(b["c"][1])


def sections(blocks: Any) -> list[tuple[dict, Section]]:
    """Every heading with its Section, numbered as LaTeX numbers them."""
    counters = [0] * (NUMBERED_LEVELS + 1)
    last = ""
    out: list[tuple[dict, Section]] = []
    for n, h in enumerate(_headers(blocks)):
        level, (ident, classes, _kv), inlines = h["c"]
        number = None
        if level <= NUMBERED_LEVELS and "unnumbered" not in classes:
            counters[level] += 1
            for deeper in range(level + 1, NUMBERED_LEVELS + 1):
                counters[deeper] = 0
            number = ".".join(str(counters[k]) for k in range(1, level + 1))
            last = number
        out.append((h, Section(ident, level, _text(inlines).strip(),
                               number, number or last, n)))
    return out


def section_table(blocks: Any) -> dict[str, Section]:
    """label -> Section, for the headings that have a label."""
    return {s.ident: s for _h, s in sections(blocks) if s.ident}
