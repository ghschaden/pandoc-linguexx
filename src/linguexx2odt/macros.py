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

r"""The document's own macros, for the text of an example.

Pandoc applies a ``\newcommand`` in the prose.  An example's text never
goes there: this converter renders it, and knew none of the document's
macros -- "An example in \lang." came out "An example in ." in the .odt
and as its source in the .docx.  So the definitions are read here, and an
example's text is expanded before it is rendered, which gives both targets
the commands the renderer knows, and the width estimate the text drawn.

Expanded as text, before rendering, rather than inside the renderer: the
fallbacks (pandoc for the .odt, the source for the .docx) then see the
expansion too, and a macro survives an unknown command beside it.

What is read: ``\newcommand``, ``\renewcommand``, ``\providecommand``,
``\DeclareRobustCommand`` (starred or not, with an argument count and an
optional first argument's default), and ``\def``/``\gdef`` with plain
``#1#2...`` parameters.  Not ``\NewDocumentCommand`` or delimited ``\def``
parameters, and not TeX's grouping: a definition applies from the start of
the document to the end, the last one winning.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from .latexutil import cmd_at, find_group, find_optional


@dataclass(frozen=True)
class Macro:
    nargs: int = 0
    default: str | None = None
    """The optional first argument's default, or None if it has none."""
    body: str = ""


_NEWCOMMAND = re.compile(
    r"\\(newcommand|renewcommand|providecommand|DeclareRobustCommand)\*?\s*"
    r"(?:\{\s*\\([a-zA-Z@]+)\s*\}|\\([a-zA-Z@]+))")
_DEF = re.compile(r"\\g?def\s*\\([a-zA-Z@]+)((?:#[1-9])*)\s*(?=\{)")

#: Nested expansion stops here: a macro that expands to itself would
#: otherwise never end.
MAX_DEPTH = 32


def collect(src: str, live: list[bool], known: frozenset[str],
            warn: Callable[[str], None]) -> dict[str, Macro]:
    r"""Every definition in *src* the expander can apply, by name.

    *known* is what already exists -- the commands the renderer and linguexx
    define.  ``\newcommand`` over one of those stops LaTeX with "already
    defined" and never takes, so here it is refused and named; ``\renew``
    is the author asking for it, and wins; ``\provide`` defers.
    """
    macros: dict[str, Macro] = {}
    spans: list[tuple[int, int]] = []

    def inside(pos: int) -> bool:
        return any(a <= pos < b for a, b in spans)

    for m in _NEWCOMMAND.finditer(src):
        if not live[m.start()] or inside(m.start()):
            continue
        kind, name = m.group(1), m.group(2) or m.group(3)
        pos = _skip(src, m.end())
        nargs, default = 0, None
        count = find_optional(src, pos)
        if count is not None and count[0].strip().isdigit():
            nargs, pos = int(count[0]), _skip(src, count[1])
            opt = find_optional(src, pos)
            if opt is not None:
                default, pos = opt[0], _skip(src, opt[1])
        body = find_group(src, pos)
        if body is None:
            continue
        spans.append((m.start(), body[1]))
        line = src.count("\n", 0, m.start()) + 1
        exists = name in known or name in macros
        if kind == "newcommand" and exists:
            warn(f"line {line}: \\newcommand\\{name}: \\{name} is already "
                 f"defined, and LaTeX refuses to redefine it with "
                 f"\\newcommand; the definition is not applied")
            continue
        if kind == "providecommand" and exists:
            continue
        macros[name] = Macro(nargs, default, body[0])

    for m in _DEF.finditer(src):
        if not live[m.start()] or inside(m.start()):
            continue
        body = find_group(src, m.end())
        if body is None:
            continue
        spans.append((m.start(), body[1]))
        macros[m.group(1)] = Macro(len(m.group(2)) // 2, None, body[0])
    return macros


def expand(latex: str, macros: dict[str, Macro],
           warn: Callable[[str], None], depth: int = 0) -> str:
    """*latex* with every use of one of *macros* replaced by its expansion,
    recursively.  A use missing an argument is left as written, and named."""
    if not macros or "\\" not in latex:
        return latex
    out: list[str] = []
    i, n = 0, len(latex)
    while i < n:
        if latex[i] != "\\":
            out.append(latex[i])
            i += 1
            continue
        hit = cmd_at(latex, i)
        if hit is None:
            out.append(latex[i])
            i += 1
            continue
        name, end = hit
        macro = macros.get(name)
        if macro is None:
            out.append(latex[i:end])
            i = end
            continue
        args, stop = _arguments(latex, end, macro)
        if args is None:
            warn(f"\\{name} is missing an argument; left as written")
            out.append(latex[i:end])
            i = end
            continue
        if depth >= MAX_DEPTH:
            warn(f"\\{name} expands more than {MAX_DEPTH} levels deep; "
                 f"left as written")
            out.append(latex[i:stop])
            i = stop
            continue
        out.append(expand(_substitute(macro.body, args), macros, warn,
                          depth + 1))
        i = stop
    return "".join(out)


def _skip(s: str, i: int) -> int:
    while i < len(s) and s[i] in " \t\n":
        i += 1
    return i


def _arguments(s: str, pos: int, macro: Macro) -> tuple[list[str] | None, int]:
    if macro.nargs == 0:
        # A control word takes the spaces after it, as TeX does: "\lang is"
        # is "Latinis", which is why authors write \lang{} or "\lang\ ".
        return [], _skip(s, pos)
    args: list[str] = []
    need = macro.nargs
    if macro.default is not None:
        opt = find_optional(s, pos)
        if opt is not None:
            args.append(opt[0])
            pos = opt[1]
        else:
            args.append(macro.default)
        need -= 1
    for _ in range(need):
        grp = find_group(s, pos)
        if grp is not None:
            args.append(grp[0])
            pos = grp[1]
            continue
        # An undelimited argument can be a single token, braces or not.
        k = _skip(s, pos)
        if k >= len(s) or s[k] in "}":
            return None, pos
        tok = cmd_at(s, k) if s[k] == "\\" else None
        stop = tok[1] if tok else k + 1
        args.append(s[k:stop])
        pos = stop
    return args, pos


def _substitute(body: str, args: list[str]) -> str:
    return re.sub(r"##|#([1-9])",
                  lambda m: "#" if m.group(0) == "##"
                  else (args[int(m.group(1)) - 1]
                        if int(m.group(1)) <= len(args) else ""),
                  body)
