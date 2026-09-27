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

r"""Stage 0 — splice ``\input`` and ``\include`` files into the source.

Done here rather than left to pandoc, for two reasons measured on pandoc
3.10.  The reader runs with ``+raw_tex``, under which it does not open
``\input{ch1}`` at all: it keeps the command as a ``RawInline "latex"``,
which both writers drop, so a chapter's prose vanished whole and the run
exited 0.  And the example scanner reads one string -- an example in a
chapter file never became a field even when pandoc did read the file.
Expanding first gives both of them the document LaTeX sees.

Files are looked for where LaTeX looks: first relative to the main
document's directory, whichever file names them, then through
``kpsewhich`` -- TeX's own lookup, so ``TEXINPUTS``, ``~/texmf`` and the
distribution, exactly as LaTeX would search them.  A shared macro file is
the case that matters: pandoc applies a ``\newcommand``, and without the
file every command it defines reached the writer raw, to be deleted.  A
file the distribution ships (``\input{glyphtounicode}``) is engine
configuration, not text: found, so not reported missing, and not spliced
in.  Without ``kpsewhich`` only the document's directory is searched, and
the warning for a missing file says so.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .latexutil import CODE, classify, cmd_at, find_group

#: \input's TeX-primitive form: ``\input chapter1`` with no braces.
_BARE_NAME = re.compile(r"[ \t]+([^\s{}%\\]+)")

_INCLUDEONLY = re.compile(r"\\includeonly(?![a-zA-Z@])")

_LINE_PREFIX = re.compile(r"line (\d+): ")


@dataclass(frozen=True)
class Expanded:
    """The spliced source, and for each of its lines the file and line it
    came from -- so that "line 212" in a warning is a line the author can
    find, not a line of a text that exists only inside this run."""

    text: str
    #: (file as written relative to the main document, or None for the
    #: main document itself; line), one per line of *text*.
    origins: tuple[tuple[str | None, int], ...]

    def locate(self, warning: str) -> str:
        """Rewrite a leading ``line N:`` to the line's own file and line.
        The main document's lines keep the bare form."""
        m = _LINE_PREFIX.match(warning)
        if m is None or not 1 <= int(m.group(1)) <= len(self.origins):
            return warning
        name, line = self.origins[int(m.group(1)) - 1]
        where = f"line {line}" if name is None else f"{name}, line {line}"
        return f"{where}: {warning[m.end():]}"


def expand_includes(src: str, workdir: Path, warn: Callable[[str], None],
                    main: Path | None = None) -> Expanded:
    """Return *src* with every live ``\\input``/``\\include`` replaced by
    the file it names, recursively.  A file that cannot be found, or that
    would include itself, is named in a warning and left out.  *main* is
    the file *src* was read from, so that including it is caught too."""
    only = _includeonly(src)
    skipped: list[str] = []
    pieces: list[tuple[str, str | None, int]] = []
    stack = (main.resolve(),) if main is not None else ()
    _expand(src, None, _Finder(workdir), warn, stack, only, skipped, pieces)
    if skipped:
        warn(f"\\includeonly: {len(skipped)} \\include'd file(s) left out, "
             f"as LaTeX leaves them out: {', '.join(skipped)}")
    return Expanded("".join(p[0] for p in pieces), _origins(pieces))


def _origins(pieces) -> tuple[tuple[str | None, int], ...]:
    """Each output line belongs to the piece holding its first character."""
    origins: list[tuple[str | None, int] | None] = [None]
    for text, name, line in pieces:
        if not text:
            continue
        if origins[-1] is None:
            origins[-1] = (name, line)
        for k, ch in enumerate(text):
            if ch == "\n":
                line += 1
                origins.append(None if k == len(text) - 1 else (name, line))
    return tuple(o or (None, 0) for o in origins)


def _includeonly(src: str) -> set[str] | None:
    kind = classify(src)
    for m in _INCLUDEONLY.finditer(src):
        if kind[m.start()] != CODE:
            continue
        grp = find_group(src, m.end())
        if grp:
            return {n.strip() for n in grp[0].split(",") if n.strip()}
    return None


def _label(path: Path, workdir: Path) -> str:
    try:
        return path.relative_to(workdir.resolve()).as_posix()
    except ValueError:
        return str(path)


class _Finder:
    """Where a named file is: beside the document, else wherever
    ``kpsewhich`` finds it.  One per run, so the distribution's roots are
    asked for once."""

    def __init__(self, workdir: Path) -> None:
        self.workdir = workdir
        self.kpsewhich = shutil.which("kpsewhich")
        self._dist: tuple[Path, ...] | None = None

    def find(self, name: str, include: bool) -> Path | None:
        # \input{x} tries x.tex before x; \include{x} only ever reads x.tex.
        names = [name + ".tex"] if include else [name + ".tex", name]
        for n in names:
            local = self.workdir / n
            if local.is_file():
                return local
        for n in names:
            found = self._kpse(n)
            if found is not None:
                return found
        return None

    def in_distribution(self, path: Path) -> bool:
        if self._dist is None:
            roots = []
            for var in ("TEXMFDIST", "TEXMFMAIN"):
                value = self._run("-var-value=" + var)
                roots += [Path(v).resolve() for v in (value or "").split(":")
                          if v.strip()]
            self._dist = tuple(roots)
        return any(path.is_relative_to(root) for root in self._dist)

    def _kpse(self, name: str) -> Path | None:
        out = self._run(name)
        path = Path(out) if out else None
        return path if path is not None and path.is_file() else None

    def _run(self, arg: str) -> str | None:
        if self.kpsewhich is None:
            return None
        try:
            proc = subprocess.run(
                [self.kpsewhich, arg], cwd=self.workdir, capture_output=True,
                text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            return None
        out = proc.stdout.strip().splitlines()
        return out[0].strip() if proc.returncode == 0 and out else None

    def where_not_found(self) -> str:
        return ("not found next to the document or by kpsewhich"
                if self.kpsewhich else
                "not found next to the document, and kpsewhich, which would "
                "search TEXINPUTS and the TeX tree, is not installed")


def _expand(src: str, label: str | None, finder: _Finder, warn,
            stack: tuple[Path, ...], only: set[str] | None,
            skipped: list[str], out: list[tuple[str, str | None, int]]) -> None:
    """Append *src*, spliced, to *out* as (text, file, first line) pieces;
    *label* is the file's name for a warning, None for the main document."""
    kind = classify(src)
    pos, i, n = 0, 0, len(src)

    def keep(a: int, b: int) -> None:
        out.append((src[a:b], label, src.count("\n", 0, a) + 1))

    def insert(text: str, at: int) -> None:
        """Text this module adds, counted as the line it was added at."""
        out.append((text, label, src.count("\n", 0, at) + 1))

    while i < n:
        if src[i] != "\\" or kind[i] != CODE:
            i += 1
            continue
        hit = cmd_at(src, i)
        if hit is None:
            i += 1
            continue
        name, end = hit
        if name == "endinput":
            # TeX finishes the line \endinput is on, then stops reading.
            eol = src.find("\n", end)
            keep(pos, i)
            keep(end, n if eol < 0 else eol + 1)
            return
        if name not in ("input", "include"):
            i = end
            continue

        grp = find_group(src, end)
        if grp is not None:
            target, stop = grp[0].strip(), grp[1]
        elif name == "input" and (m := _BARE_NAME.match(src, end)):
            target, stop = m.group(1), m.end()
        else:
            i = end
            continue
        keep(pos, i)
        pos = i = stop

        written = f"\\{name}{{{target}}}"
        if name == "include" and only is not None and target not in only:
            skipped.append(target)
            continue
        found = finder.find(target, name == "include")
        if found is None:
            warn(f"{written}: {finder.where_not_found()}; "
                 f"what it contains is not in the output")
            continue
        found = found.resolve()
        if finder.in_distribution(found):
            continue
        if found in stack:
            warn(f"{written}: {found.name} includes itself; "
                 f"the repetition is left out")
            continue

        # \include is \clearpage, file, \clearpage: never inside a paragraph.
        if name == "include":
            insert("\n\n", stop)
        start = len(out)
        _expand(found.read_text(encoding="utf-8"),
                _label(found, finder.workdir), finder, warn, (*stack, found),
                only, skipped, out)
        # A file ends a line: without this, a comment on its last line
        # would swallow whatever follows the \input on the including line.
        if not "".join(p[0] for p in out[start:]).endswith("\n"):
            insert("\n", stop)
        if name == "include":
            insert("\n", stop)
    keep(pos, n)
