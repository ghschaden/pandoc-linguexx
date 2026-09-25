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

"""Small brace-aware LaTeX scanning helpers.

Not a LaTeX parser — just enough structure-awareness to find command
boundaries, respect brace groups, and know which characters are "live"
(i.e. not inside a comment or a verbatim span).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CMD = re.compile(r"\\(?:([a-zA-Z@]+)\*?|(.))")
"""A control sequence: a word (optionally starred) or a single character."""

VERB_ENVS = ("verbatim", "Verbatim", "lstlisting", "minted", "alltt")


def cmd_at(s: str, i: int) -> tuple[str, int] | None:
    """If a control sequence starts at *i*, return (name, end index)."""
    m = CMD.match(s, i)
    if not m:
        return None
    return (m.group(1) or m.group(2)), m.end()


CODE, COMMENT, VERBATIM = 0, 1, 2


def classify(s: str) -> list[int]:
    """Tag every character CODE, COMMENT or VERBATIM.

    Comments are ``%`` to end of line when not escaped; verbatim spans are
    ``\\verb|…|`` and ``\\begin{verbatim}…\\end{verbatim}`` and friends.
    Both are invisible to the example scanner, but only comments may be
    *deleted* — a ``\\verb`` in an example body is real content.
    """
    kind = [CODE] * len(s)
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            hit = cmd_at(s, i)
            if hit is None:
                i += 1
                continue
            name, end = hit
            if name == "verb":
                # \verb<delim>…<delim>; the delimiter is the next character
                if end < n:
                    delim = s[end]
                    close = s.find(delim, end + 1)
                    close = n if close < 0 else close + 1
                    for k in range(i, close):
                        kind[k] = VERBATIM
                    i = close
                    continue
            if name == "begin":
                m = re.match(r"\s*\{([^}]*)\}", s[end:])
                if m and m.group(1) in VERB_ENVS:
                    stop = s.find("\\end{" + m.group(1) + "}", end)
                    stop = n if stop < 0 else stop + len("\\end{" + m.group(1) + "}")
                    for k in range(i, stop):
                        kind[k] = VERBATIM
                    i = stop
                    continue
            i = end  # an escaped char such as \% is code, and is skipped whole
            continue
        if c == "%":
            j = s.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                kind[k] = COMMENT
            i = j
            continue
        i += 1
    return kind


def live_mask(s: str) -> list[bool]:
    """Characters the example scanner may look at."""
    return [k == CODE for k in classify(s)]


def strip_comments(s: str) -> str:
    """Delete comments only.  Verbatim spans are content and stay put;
    newlines survive so blank-line structure is unchanged."""
    kind = classify(s)
    return "".join(
        c for i, c in enumerate(s) if kind[i] != COMMENT or c == "\n"
    )


def find_group(s: str, i: int) -> tuple[str, int] | None:
    """Read a ``{…}`` group starting at (or after whitespace from) *i*.

    Returns (contents without the outer braces, index just past the group).
    """
    j = i
    while j < len(s) and s[j] in " \t\n":
        j += 1
    if j >= len(s) or s[j] != "{":
        return None
    depth, k = 0, j
    while k < len(s):
        if s[k] == "\\":
            k += 2
            continue
        if s[k] == "{":
            depth += 1
        elif s[k] == "}":
            depth -= 1
            if depth == 0:
                return s[j + 1 : k], k + 1
        k += 1
    return None


def find_optional(s: str, i: int) -> tuple[str, int] | None:
    """Read a ``[…]`` optional argument starting at *i* (no whitespace skip)."""
    if i >= len(s) or s[i] != "[":
        return None
    depth, k = 0, i
    while k < len(s):
        if s[k] == "\\":
            k += 2
            continue
        if s[k] == "[":
            depth += 1
        elif s[k] == "]":
            depth -= 1
            if depth == 0:
                return s[i + 1 : k], k + 1
        k += 1
    return None


def split_top(s: str, pattern: re.Pattern[str]) -> list[tuple[str, str]]:
    """Split *s* at matches of *pattern* occurring at brace depth 0.

    Returns [(matched_text, chunk_after)], with the first entry's match
    being '' for the text before the first separator.
    """
    out: list[tuple[str, str]] = []
    depth, i, start, sep = 0, 0, 0, ""
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            m = pattern.match(s, i) if depth == 0 else None
            if m:
                out.append((sep, s[start : m.start()]))
                sep, start = m.group(0), m.end()
                i = m.end()
                continue
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth = max(0, depth - 1)
        elif depth == 0:
            m = pattern.match(s, i)
            if m:
                out.append((sep, s[start : m.start()]))
                sep, start = m.group(0), m.end()
                i = m.end()
                continue
        i += 1
    out.append((sep, s[start:]))
    return out


def split_cells(tier: str) -> tuple[str, ...]:
    """Split a gloss tier into columns.

    Whitespace separates columns at brace depth 0; a ``{braced group}``
    is one column with its outer braces removed (linguexx's documented
    "braced group = one column").
    """
    cells: list[str] = []
    buf: list[str] = []
    depth, i, n = 0, 0, len(tier)
    braced_whole = False

    def flush() -> None:
        nonlocal braced_whole
        tok = "".join(buf).strip()
        buf.clear()
        if not tok:
            braced_whole = False
            return
        if braced_whole and tok.startswith("{") and tok.endswith("}"):
            tok = tok[1:-1].strip()
        cells.append(tok)
        braced_whole = False

    while i < n:
        c = tier[i]
        if c == "\\":
            buf.append(tier[i : i + 2])
            i += 2
            continue
        if c == "{":
            if depth == 0 and not "".join(buf).strip():
                braced_whole = True
            depth += 1
        elif c == "}":
            depth = max(0, depth - 1)
        elif depth == 0 and c.isspace():
            flush()
            i += 1
            continue
        buf.append(c)
        i += 1
    flush()
    return tuple(cells)


# --------------------------------------------------------------------------
# the characters linguexx puts around a number
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Brackets:
    r"""What linguexx wraps an example number and a sub-example letter in.

    The defaults are linguexx's own (``linguexx.sty``)::

        \ExLBr ( \ExRBr )                -> (1)
        \SubExLBr '' \SubExRBr .         -> a.
        \SubSubExLBr '' \SubSubExRBr .   -> i.

    They are `linguex`'s names and a document is entitled to redefine them
    -- ``\renewcommand{\ExLBr}{[}`` for ``[1]`` is the documented way to get
    square brackets, and linguexx has honoured it since 1.3.  Before that
    the redefinition was accepted and ignored, which its changelog calls
    "the one kind of incompatibility a drop-in replacement cannot have: the
    document still compiles and only the page is wrong".  This converter
    reproduced exactly that until the same version it now targets.
    """

    ex_l: str = "("
    ex_r: str = ")"
    sub_l: str = ""
    sub_r: str = "."
    subsub_l: str = ""
    subsub_r: str = "."

    def wrap_example(self, inner: str) -> str:
        return f"{self.ex_l}{inner}{self.ex_r}"

    def wrap_sub(self, level: int, inner: str) -> str:
        if level >= 2:
            return f"{self.subsub_l}{inner}{self.subsub_r}"
        return f"{self.sub_l}{inner}{self.sub_r}"


#: The six names, and which field of Brackets each one sets.
_BRACKET_FIELDS = {
    "ExLBr": "ex_l", "ExRBr": "ex_r",
    "SubExLBr": "sub_l", "SubExRBr": "sub_r",
    "SubSubExLBr": "subsub_l", "SubSubExRBr": "subsub_r",
}

_BRACKET_DEF = re.compile(
    r"\\(?:re)?newcommand\s*\*?\s*(?:\{\s*\\([a-zA-Z@]+)\s*\}|\\([a-zA-Z@]+))"
    r"|\\def\s*\\([a-zA-Z@]+)"
)


def scan_brackets(src: str, warn=None) -> Brackets:
    r"""Read ``\ExLBr`` & co. out of a document's preamble.

    Only the preamble counts.  An ODT example number is a `text:sequence`
    field and its surrounding characters are literal text emitted once per
    example, so a redefinition partway through the document cannot be
    honoured the way LaTeX honours it; the run says so rather than
    pretending.  Comments are skipped -- a commented-out ``\renewcommand``
    is the obvious way to try one out and put it back.
    """
    live = live_mask(src)
    body_at = src.find(r"\begin{document}")
    if body_at < 0:
        body_at = len(src)

    values: dict[str, str] = {}
    for m in _BRACKET_DEF.finditer(src):
        if not live[m.start()]:
            continue
        name = m.group(1) or m.group(2) or m.group(3)
        field_name = _BRACKET_FIELDS.get(name)
        if field_name is None:
            continue
        group = find_group(src, m.end())
        if group is None:
            continue
        if m.start() > body_at:
            if warn:
                warn(f"\\{name} is redefined after \\begin{{document}}; "
                     f"ignored -- an example number's brackets are emitted "
                     f"once per example and cannot change partway through")
            continue
        values[field_name] = group[0].strip()

    return Brackets(**values)


#: How a document names its bibliography.  biblatex's \addbibresource takes
#: a filename with its extension; bibtex's \bibliography takes a
#: comma-separated list of stems without one.
_BIB_CMD = re.compile(r"\\(addbibresource|bibliography)\s*(?=[\[{])")


def scan_bibliography(src: str) -> list[str]:
    r"""The .bib files a document declares, in the order it declares them.

    Both spellings, because a linguistics paper is as likely to be biblatex
    as bibtex, and the difference is only whether the extension is written
    out.  Comments are skipped: an author swapping bibliographies comments
    the old line out, and picking up both would be picking up one they
    deliberately turned off.
    """
    live = live_mask(src)
    out: list[str] = []
    for m in _BIB_CMD.finditer(src):
        if not live[m.start()]:
            continue
        i = m.end()
        if src[i : i + 1] == "[":          # \addbibresource[label=...]{...}
            opt = find_optional(src, i)
            if opt is None:
                continue
            i = opt[1]
        group = find_group(src, i)
        if group is None:
            continue
        for name in group[0].split(","):
            name = name.strip()
            if not name:
                continue
            if m.group(1) == "bibliography" and not name.endswith(".bib"):
                name += ".bib"
            if name not in out:
                out.append(name)
    return out
