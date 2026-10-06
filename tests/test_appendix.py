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
r"""\appendix, and \numberwithin{equation}{section}.

Pandoc deletes \appendix without a trace, so the sections after it went on
counting, "2" and "2.1" where LaTeX prints "A" and "A.1" -- in the headings
and in every reference.  And equations were numbered through the document
where \numberwithin restarts them at each section, "(1.2)".

The expected text is what LaTeX prints, read off ``pdflatex`` and
``pdftotext``.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from linguexx2odt import postprocess
from linguexx2odt.cli import main

pandoc = pytest.mark.skipif(shutil.which("pandoc") is None,
                            reason="pandoc not installed")
soffice = pytest.mark.skipif(shutil.which("soffice") is None
                             or shutil.which("pdftotext") is None,
                             reason="libreoffice or pdftotext not installed")

SOURCE = r"""\documentclass{article}
\usepackage{amsmath}
\usepackage{hyperref}
\usepackage{cleveref}
%WITHIN%
\begin{document}
\section{Intro}\label{s1}
\begin{equation}\label{e0} z \end{equation}
\begin{equation}\label{e1} a \end{equation}
\appendix
\section{Data}\label{a1}
\subsection{More}\label{a11}
\begin{equation}\label{e2} b \end{equation}
\section{Code}\label{a2}

APP: A \ref{a1} B \ref{a11} C \cref{a1} D \Cref{a11} E \autoref{a1} F \autoref{a11}
G \cref{a1,a2} H \nameref{a2} I \eqref{e2} J \cref{s1,a1} K \cref{e0,e1} L \ref{e2}.
\end{document}
"""

HEADINGS = ["1 Intro", "A Data", "A.1 More", "B Code"]

#: LaTeX's rendering, without and with \numberwithin{equation}{section}.
LATEX = {
    "": ["z (1)", "a (2)", "b (3)",
         "APP: A A B A.1 C section A D Section A.1 E Appendix A F subsection A.1 "
         "G sections A and B H Code I (3) J sections 1 and A K eqs. (1) and (2) L 3."],
    r"\numberwithin{equation}{section}": [
        "z (1.1)", "a (1.2)", "b (A.1)",
        "APP: A A B A.1 C section A D Section A.1 E Appendix A F subsection A.1 "
        "G sections A and B H Code I (A.1) J sections 1 and A K eqs. (1.1) and (1.2) L A.1."],
}


def _convert(tmp_path: Path, within: str, target: str) -> Path:
    tex = tmp_path / "doc.tex"
    tex.write_text(SOURCE.replace("%WITHIN%", within), encoding="utf-8")
    out = tmp_path / f"doc.{target}"
    assert main([str(tex), "-o", str(out), "--to", target, "-q"]) == 0
    return out


@pandoc
@soffice
@pytest.mark.parametrize("target", ["odt", "docx"])
@pytest.mark.parametrize("within", sorted(LATEX))
def test_the_appendix_is_lettered_as_latex_letters_it(
        tmp_path: Path, within: str, target: str) -> None:
    out = _convert(tmp_path, within, target)
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf",
                    "--outdir", str(tmp_path), str(out)],
                   check=True, capture_output=True, timeout=120)
    txt = subprocess.run(["pdftotext", "-layout", str(out.with_suffix(".pdf")), "-"],
                         check=True, capture_output=True, text=True).stdout
    lines = [" ".join(line.split()) for line in txt.splitlines() if line.strip()]
    text = " ".join(lines)
    for heading in HEADINGS:
        assert heading in lines, f"{heading!r} not a line of:\n{lines}"
    for line in LATEX[within]:
        assert line in text, f"{line!r} not in:\n{text}"


@pandoc
def test_a_docx_caches_the_letters(tmp_path: Path) -> None:
    """The cache is what a reader that never updates fields shows."""
    xml = postprocess.read(_convert(tmp_path, "", "docx"), "word/document.xml")
    para = next(p for p in re.findall(r"<w:p\b.*?</w:p>", xml, re.S) if "APP:" in p)
    shown = " ".join("".join(re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", para))
                     .replace(" ", " ").split())
    assert shown == LATEX[""][-1], shown
