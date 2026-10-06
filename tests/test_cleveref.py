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
r"""\cref with several labels, a range, and \cref to an example.

All three were deleted with a warning -- \cref{x} to an example too, which
linguexx prints "(1)".  The expected text is what cleveref prints, read off
``pdflatex`` and ``pdftotext`` (plan-crossrefs.md).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from linguexx2odt.cleveref import Entry, phrase
from linguexx2odt.cli import main

pandoc = pytest.mark.skipif(shutil.which("pandoc") is None,
                            reason="pandoc not installed")
soffice = pytest.mark.skipif(shutil.which("soffice") is None
                             or shutil.which("pdftotext") is None,
                             reason="libreoffice or pdftotext not installed")


def _say(entries: list[tuple[str, tuple | None, str]], capital: bool = False) -> str:
    parts = phrase([Entry(kind, key, text) for kind, key, text in entries], capital)
    return "".join(p if isinstance(p, str) else p.target for p in parts).replace(" ", " ")


def S(n: int) -> tuple[str, tuple, str]:
    return ("section", (n,), str(n))


@pytest.mark.parametrize("entries,capital,latex", [
    ([S(1), S(2)], False, "sections 1 and 2"),
    ([S(1), S(2), S(3)], False, "sections 1 to 3"),
    ([S(1), S(3), S(5)], False, "sections 1, 3 and 5"),
    ([S(1), S(2), S(3), S(5)], False, "sections 1 to 3 and 5"),
    ([S(2), S(1)], True, "Sections 1 and 2"),
    ([S(1), ("table", (1,), "1")], False, "section 1 and table 1"),
    ([("equation", (1,), "(1)"), ("equation", (2,), "(2)")], False, "eqs. (1) and (2)"),
    ([S(1), ("table", (1,), "1"), ("equation", (1,), "(1)")], False,
     "section 1, table 1, and eq. (1)"),
    ([("equation", (1,), "(1)"), S(4), ("table", (1,), "1")], True,
     "Equation (1), section 4, and table 1"),
    ([S(1), ("table", (1,), "1"), S(2)], False, "sections 1 and 2 and table 1"),
    ([("example", (0,), "(1)"), ("example", (1,), "(2)"), ("example", (3,), "(4)")], False,
     "(1), (2) and (4)"),
    ([("example", (2, "a"), "(3a)"), ("example", (2, "b"), "(3b)")], True, "(3a) and (3b)"),
    ([("table", (1,), "1"), ("table", (1,), "1")], False, "table 1"),
    ([("example", (0,), "(1)"), S(1)], False, "(1) and section 1"),
])
def test_cleverefs_phrasing(entries, capital, latex) -> None:
    assert _say(entries, capital) == latex


SOURCE = r"""\documentclass{article}
\usepackage{amsmath}
\usepackage{linguexx}
\usepackage{hyperref}
\usepackage{cleveref}
\begin{document}
\section{A}\label{s1}\section{B}\label{s2}\section{C}\label{s3}
\begin{table}[h]\caption{T}\label{t1}\begin{tabular}{l} x \\ \end{tabular}\end{table}

\ex.\label{x1} One.

\ex.\label{x2} Two.

\ex.\label{x3} Three.

R1: \cref{x1}. R2: \cref{x1,x2,x3}. R3: \Cref{s3,s1,t1}. R4: \crefrange{s1}{s3}.
R5: \cref{x2,s2}.
\end{document}
"""

#: cleveref's (and linguexx's, for the examples) rendering of SOURCE.
LATEX = "R1: (1). R2: (1) to (3). R3: Sections 1 and 3 and table 1. R4: sections 1 to 3. " \
        "R5: (2) and section 2."


@pandoc
@soffice
@pytest.mark.parametrize("target", ["odt", "docx"])
def test_a_cref_list_prints_what_cleveref_prints(tmp_path: Path, target: str) -> None:
    tex = tmp_path / "doc.tex"
    tex.write_text(SOURCE, encoding="utf-8")
    out = tmp_path / f"doc.{target}"
    assert main([str(tex), "-o", str(out), "--to", target, "-q"]) == 0
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf",
                    "--outdir", str(tmp_path), str(out)],
                   check=True, capture_output=True, timeout=120)
    text = " ".join(subprocess.run(["pdftotext", str(out.with_suffix(".pdf")), "-"],
                                   check=True, capture_output=True, text=True).stdout.split())
    assert LATEX in text, text


@pandoc
def test_a_cref_list_is_no_warning(tmp_path: Path, capsys) -> None:
    tex = tmp_path / "doc.tex"
    tex.write_text(SOURCE, encoding="utf-8")
    assert main([str(tex), "-o", str(tmp_path / "doc.odt"), "--to", "odt"]) == 0
    err = capsys.readouterr().err
    assert "deleted from the output" not in err and "??" not in err, err
