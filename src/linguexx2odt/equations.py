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
r"""Display equations, numbered as LaTeX numbers them (plan-crossrefs.md).

Pandoc writes a display equation without its number, so a reference to one
pointed at nothing on the page.  This reads the number off the source the
way amsmath assigns it: ``equation`` and ``multline`` once; ``align``,
``gather``, ``alignat``, ``flalign`` and ``eqnarray`` once per row, a row
with ``\nonumber`` or ``\notag`` none; ``\tag{x}`` prints "(x)" and steps
nothing; a starred environment, ``\[ \]`` and ``displaymath`` none.

The numbers are text, and so is a reference to one: the user's decision
(equations stay text), so neither follows a renumbering.

The source is read, not pandoc's AST: pandoc 3.6 gives an `equation` as
its bare body and an `align` as `aligned`, so the AST cannot tell
`equation` from `equation*`, nor which rows an `align` numbers (3.10 keeps
the environment).  The residue pandoc reads holds the same displays in the
same order (display_math), and the k-th numbers pandoc's k-th.

Format-agnostic: no markup here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

ONCE = frozenset({"equation", "multline"})
PER_ROW = frozenset({"align", "gather", "alignat", "flalign", "eqnarray"})

_ENV = re.compile(r"\s*\\begin\{(\w+)(\*?)\}(.*)\\end\{\1\*?\}\s*", re.S)
_LABEL = re.compile(r"\\label\s*\{([^}]*)\}")
_TAG = re.compile(r"\\tag\*?\s*\{([^}]*)\}")
_NONUMBER = re.compile(r"\\(?:nonumber|notag)\b")


def _tag_text(tag: str) -> str:
    r"""\tag{$*$} prints "(∗)": the tag as text, a "*" in its math the
    math asterisk, its math shifts gone."""
    return re.sub(r"\$([^$]*)\$", lambda m: m.group(1).replace("*", "\u2217"),
                  tag).strip()


@dataclass
class Row:
    math: str
    """TeX for the row, with \\label, \\tag and \\nonumber taken out."""
    number: str | None = None
    r"""What \ref prints, "1" or a tag's text; None for no number."""
    labels: list[str] = field(default_factory=list)
    tagged: bool = False
    """Numbered by \\tag, which no counter touches."""


def _clean(tex: str) -> str:
    tex = _LABEL.sub("", tex)
    tex = _TAG.sub("", tex)
    return _NONUMBER.sub("", tex).strip()


def _rows(body: str) -> list[str]:
    r"""*body* split at its own \\, not at one in a group or a nested
    environment (aligned, cases, a matrix)."""
    rows, depth, envs, start, i = [], 0, 0, 0, 0
    while i < len(body):
        c = body[i]
        if c == "\\":
            if body.startswith("\\\\", i) and depth == 0 and envs == 0:
                rows.append(body[start:i])
                i += 2
                opt = re.match(r"\s*\[[^\]]*\]", body[i:])     # \\[2pt]
                if opt:
                    i += opt.end()
                start = i
                continue
            if body.startswith("\\begin", i):
                envs += 1
            elif body.startswith("\\end", i):
                envs -= 1
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    rows.append(body[start:])
    return [r for r in rows if r.strip()]


#: Marks a number that came from \tag, until number_rows hands it back.
TAGGED = "\x00"


_DISPLAY = re.compile(
    r"\\begin\{(equation|align|gather|multline|flalign|alignat|eqnarray|displaymath)"
    r"(\*?)\}|\\\[|\$\$")


def display_math(src: str) -> list[str]:
    """The display equations of *src* as written, in order: what pandoc
    makes a DisplayMath of.  Comments and verbatim are skipped."""
    from .latexutil import live_mask

    live = live_mask(src)
    out: list[str] = []
    i = 0
    while True:
        m = _DISPLAY.search(src, i)
        if m is None:
            return out
        if not live[m.start()]:
            i = m.end()
            continue
        if m.group(1):
            close = f"\\end{{{m.group(1)}{m.group(2)}}}"
        else:
            close = "\\]" if m.group(0) == "\\[" else "$$"
        end = src.find(close, m.end())
        if end < 0:
            return out
        end += len(close)
        tex = src[m.start():end]
        # \[ \] and $$ $$ are written as displaymath, which numbers nothing
        if not m.group(1):
            tex = "\\begin{displaymath}" + src[m.end():end - len(close)] + "\\end{displaymath}"
        out.append(tex)
        i = end


def _shown(tex: str) -> str:
    """The TeX to typeset a whole display from: pandoc's, its environment
    dropped where it is a bare equation (3.10 keeps it, 3.6 does not)."""
    m = _ENV.fullmatch(tex)
    if m and m.group(1) in ("equation", "displaymath"):
        return _clean(m.group(3))
    return _clean(tex)


def number_rows(tex: str, counter: list[int], shown: str | None = None) -> list[Row]:
    """*tex* as written decides the numbers; *shown*, pandoc's TeX for it,
    is what a row that is not split is typeset from."""
    rows = _number_rows(tex, counter)
    if shown is not None and len(rows) == 1:
        rows[0].math = _shown(shown)
    for r in rows:
        if r.number is not None and r.number.startswith(TAGGED):
            r.number, r.tagged = r.number[len(TAGGED):], True
    return rows


def _number_rows(tex: str, counter: list[int]) -> list[Row]:
    """The rows of display math *tex*, numbered from *counter* (a one-item
    list, stepped in place).  One row unless several are numbered: those
    are split, so that each number stands beside its own row."""
    m = _ENV.fullmatch(tex)
    if m is None:
        return [Row(tex.strip())]
    env, star, body = m.groups()
    if star or (env not in ONCE and env not in PER_ROW):
        tag = _TAG.search(body)
        return [Row(_clean(tex),
                    TAGGED + _tag_text(tag.group(1)) if tag else None,
                    _LABEL.findall(body))]

    def number(part: str) -> str | None:
        tag = _TAG.search(part)
        if tag:
            return TAGGED + _tag_text(tag.group(1))
        if _NONUMBER.search(part):
            return None
        counter[0] += 1
        return str(counter[0])

    if env in ONCE:
        # equation's body alone; multline keeps its environment, which
        # breaks its lines
        math = _clean(body) if env == "equation" else _clean(tex)
        return [Row(math, number(body), _LABEL.findall(body))]

    if env == "alignat":
        body = re.sub(r"^\s*\{[^}]*\}", "", body)
    parts = _rows(body)
    numbers = [number(p) for p in parts]
    if sum(n is not None for n in numbers) <= 1:
        return [Row(_clean(tex), next((n for n in numbers if n), None),
                    _LABEL.findall(body))]
    return [Row(_clean(p).replace("&", ""), n, _LABEL.findall(p))
            for p, n in zip(parts, numbers)]


@dataclass(frozen=True)
class Equation:
    ident: str
    number: str
    r"""What \ref prints: "1", "1.2" under \numberwithin, or a \tag's text."""
    serial: int
    section: Any
    r"""The heading before it, whose title \nameref prints."""
    key: tuple | None = None
    r"""Its number to sort by, for \cref: (1,) or (0, 1, 2); None for a tag."""

    @property
    def bookmark(self) -> str:
        """Around the number beside the equation, for \\pageref."""
        return f"_Reflxeq{self.serial}"


def within(src: str) -> int | None:
    r"""The heading level \numberwithin{equation}{x} (or \counterwithin)
    numbers equations within, from the preamble: pandoc makes \chapter
    level 1 where a document has one, \section otherwise."""
    m = re.search(r"\\(?:numberwithin|counterwithin)\s*\{equation\}\s*\{(\w+)\}", src)
    if m is None:
        return None
    levels = ["section", "subsection", "subsubsection"]
    if re.search(r"\\chapter\b", src):
        levels = ["chapter"] + levels
    return levels.index(m.group(1)) + 1 if m.group(1) in levels else None


#: Where equations' serials start (sections.targets): above every other
#: target's, so that their bookmarks never meet.
SERIAL_BASE = 100000


@dataclass
class EquationTargets:
    rows: dict[int, list[Row]]
    """id(Math node) -> its rows, for every display equation that has a
    number."""
    equations: list[Equation]
    row_serials: dict[int, int]
    """id(Row) -> its serial, for every numbered row."""


def _display_nodes(node: Any) -> int:
    if isinstance(node, list):
        return sum(_display_nodes(x) for x in node)
    if not isinstance(node, dict):
        return 0
    if node.get("t") == "Math":
        return int(node["c"][0].get("t") == "DisplayMath")
    if node.get("t") in ("RawInline", "RawBlock", "Str", "Code", "CodeBlock"):
        return 0
    return _display_nodes(node.get("c"))


def equation_targets(blocks: Any, heads: dict[int, Any],
                     within: int | None = None,
                     sources: list[str] | None = None,
                     warn=lambda _m: None) -> EquationTargets:
    r"""*within*: the heading level \numberwithin{equation}{...} names --
    the counter restarts there and the number is that heading's, "1.2".
    *sources*: display_math of what pandoc read, one per DisplayMath."""
    if sources is not None and len(sources) != _display_nodes(blocks):
        warn(f"{len(sources)} display equations in the source, "
             f"{_display_nodes(blocks)} in what pandoc made of it: numbered "
             "from pandoc's, which may not say which are starred")
        sources = None
    seen = [0]
    counter = [0]
    prefix: list[Any] = [None]
    serial = [SERIAL_BASE]
    rows: dict[int, list[Row]] = {}
    equations: list[Equation] = []
    row_serials: dict[int, int] = {}
    section: list[Any] = [None]

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for x in node:
                walk(x)
            return
        if not isinstance(node, dict):
            return
        t = node.get("t")
        if t == "Header" and id(node) in heads:
            section[0] = heads[id(node)]
            sec = heads[id(node)]
            if within is not None and sec.number and sec.level <= within:
                counter[0] = 0
                prefix[0] = sec
        if t == "Math":
            kind, tex = node["c"]
            if kind.get("t") != "DisplayMath":
                return
            written = sources[seen[0]] if sources is not None else tex
            seen[0] += 1
            numbered = number_rows(written, counter, tex)
            if any(r.number is not None for r in numbered):
                rows[id(node)] = numbered
                for r in numbered:
                    if r.number is None:
                        continue
                    key = None if r.tagged else (int(r.number),)
                    if within is not None and not r.tagged:
                        # "1.2": the heading's number at that level, then its own
                        sec = prefix[0]
                        parts = sec.shown.split(".")[:within] if sec else ["0"]
                        key = ((int(sec.appendix),) + sec.numbers[:within] if sec else (0,)) + key
                        r.number = ".".join(parts + [r.number])
                    row_serials[id(r)] = serial[0]
                    for label in r.labels:
                        equations.append(Equation(label, r.number, serial[0],
                                                  section[0], key))
                    serial[0] += 1
            return
        if t in ("RawInline", "RawBlock", "Str", "Code", "CodeBlock"):
            return
        walk(node.get("c"))

    walk(blocks)
    return EquationTargets(rows, equations, row_serials)
