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
r"""Numbered equations, and references to them (plan-crossrefs.md, step 4).

Pandoc wrote display equations with no number, and a reference to one was
deleted with a warning.  The numbers are written now, beside each equation
as LaTeX sets them, and a reference prints what LaTeX prints -- as text,
the user's decision for equations; only a page is a field.

The expected text is not reasoned out: it is what LaTeX prints for SOURCE
(article, amsmath, hyperref, cleveref), read off ``pdflatex`` and
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

from equationxml import equation_paragraphs, math_objects

pandoc = pytest.mark.skipif(shutil.which("pandoc") is None,
                            reason="pandoc not installed")
soffice = pytest.mark.skipif(shutil.which("soffice") is None
                             or shutil.which("pdftotext") is None,
                             reason="libreoffice or pdftotext not installed")

SOURCE = r"""\documentclass{article}
\usepackage{amsmath}
\usepackage{linguexx}
\usepackage{hyperref}
\usepackage{cleveref}
\begin{document}
\section{Intro}
Before the math
\begin{equation}\label{eq:a} a = b \end{equation}
\begin{equation*} c = d \end{equation*}
and prose after it.
\begin{align}
x &= y \label{eq:x}\\
z &= w \nonumber\\
u &= v \label{eq:u}
\end{align}
\[ e = f \]
\begin{equation}\label{eq:g} g = h \end{equation}

REFS: A \ref{eq:a} B \eqref{eq:x} C \cref{eq:u} D \Cref{eq:g} E \autoref{eq:a}
F \nameref{eq:a} G \pageref{eq:g} H \eqref{t}.
\begin{equation} k \tag{$*$}\label{t}\end{equation}
\end{document}
"""

#: LaTeX's numbering of SOURCE, numbered display by numbered display: a=b
#: (1); the align's x=y (2), z=w none, u=v (3); g=h (4); k (∗).  c=d and
#: e=f have no number, and stay as pandoc writes them.
NUMBERS = ["(1)", "(2)", None, "(3)", "(4)", "(∗)"]
LATEX_REFS = ("REFS: A 1 B (2) C eq. (3) D Equation (4) E Equation 1 F Intro"
              " G 1 H (∗).")


def _convert(tmp_path: Path, target: str, quiet: bool = True) -> Path:
    tex = tmp_path / "doc.tex"
    tex.write_text(SOURCE, encoding="utf-8")
    out = tmp_path / f"doc.{target}"
    args = [str(tex), "-o", str(out), "--to", target] + (["-q"] if quiet else [])
    assert main(args) == 0
    return out


def _text(doc: Path) -> str:
    """The laid-out page as one line of text."""
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf",
                    "--outdir", str(doc.parent), str(doc)],
                   check=True, capture_output=True, timeout=120)
    txt = subprocess.run(["pdftotext", str(doc.with_suffix(".pdf")), "-"],
                         check=True, capture_output=True, text=True).stdout
    return " ".join(txt.split())


@pandoc
@pytest.mark.parametrize("target", ["odt", "docx"])
def test_equations_are_numbered_as_latex_numbers_them(tmp_path: Path, target: str) -> None:
    """Read from the file, not off the page: what a PDF gives for a
    formula's text depends on the LibreOffice that made it (equationxml)."""
    out = _convert(tmp_path, target)
    assert equation_paragraphs(out) == [(True, n) for n in NUMBERS]
    assert math_objects(out) == len(NUMBERS) + 2       # c=d and e=f, unnumbered


@pandoc
@soffice
@pytest.mark.parametrize("target", ["odt", "docx"])
def test_the_prose_stays_and_a_reference_prints_what_latex_prints(
        tmp_path: Path, target: str) -> None:
    text = _text(_convert(tmp_path, target))
    assert "Before the math" in text and "and prose after it." in text, text
    # Any page for G: it is the layout's, which an older LibreOffice's
    # taller formulas push to page 2 (CI).  test_pages holds a page to the
    # one LibreOffice's own PDF shows.
    refs = re.escape(LATEX_REFS).replace(r"G\ 1", r"G\ \d+")
    assert re.search(refs, text), text


@pandoc
def test_a_reference_to_an_equation_is_text_but_its_page(tmp_path: Path) -> None:
    xml = postprocess.read(_convert(tmp_path, "docx"), "word/document.xml")
    para = next(p for p in re.findall(r"<w:p\b.*?</w:p>", xml, re.S) if "REFS" in p)
    fields = re.findall(r"<w:instrText[^>]*> (\w+) ", para)
    # \nameref's section title and \pageref's page; the rest is text
    assert sorted(fields) == ["PAGEREF", "REF"], fields


@pandoc
def test_a_reference_to_an_equation_is_no_warning(tmp_path: Path, capsys) -> None:
    _convert(tmp_path, "odt", quiet=False)
    err = capsys.readouterr().err
    assert "deleted from the output" not in err, err


def test_amsmath_numbering() -> None:
    from linguexx2odt.equations import number_rows

    counter = [0]

    def rows(tex: str) -> list[tuple[str, str | None]]:
        return [(r.math, r.number) for r in number_rows(tex, counter)]

    assert rows(r"\begin{equation}\label{a} a = b\end{equation}") == [("a = b", "1")]
    assert rows(r"\begin{equation*} c\end{equation*}")[0][1] is None
    assert rows(r"e = f") == [("e = f", None)]
    # several numbers: a row each, the alignment marks gone
    assert rows(r"\begin{align}x &= y \\ z &= w \nonumber\\[2pt] u &= v\end{align}") \
        == [("x = y", "2"), ("z = w", None), ("u = v", "3")]
    # one number: kept whole, so the alignment stays
    whole = rows(r"\begin{align}x &= y \\ z &= w \notag\end{align}")
    assert len(whole) == 1 and whole[0][1] == "4" and "&" in whole[0][0]
    # a \\ inside an environment of the row is not a row
    assert len(rows(r"\begin{gather} p = \begin{cases} 1 \\ 2 \end{cases} \\ q\end{gather}")) == 2
    # \tag prints its text and steps nothing
    assert rows(r"\begin{equation} k \tag{A}\end{equation}") == [("k", "A")]
    assert rows(r"\begin{equation} m \end{equation}") == [("m", "7")]


def test_the_numbers_come_from_the_source_not_pandocs_ast() -> None:
    r"""pandoc 3.6 gives `equation` as its bare body and `equation*` the
    same way, so the AST cannot say which is numbered; the source can."""
    from linguexx2odt.equations import display_math, equation_targets

    src = (r"A \begin{equation}\label{a} x \end{equation} B \[ y \] "
           r"% \begin{equation} commented \end{equation}" "\n"
           r"\begin{equation*} z \end{equation*} \begin{equation}\label{b} w \end{equation}")
    written = display_math(src)
    assert len(written) == 4 and written[1].startswith(r"\begin{displaymath}")

    def math(tex: str) -> dict:
        return {"t": "Math", "c": [{"t": "DisplayMath"}, tex]}
    # what pandoc 3.6.1 makes of it: environments gone
    blocks = [{"t": "Para", "c": [math(r"\label{a} x"), math("y"), math("z"),
                                  math(r"\label{b} w")]}]
    found = equation_targets(blocks, {}, sources=written)
    assert [(e.ident, e.number) for e in found.equations] == [("a", "1"), ("b", "2")]
    assert [r.math for rows in found.rows.values() for r in rows] == ["x", "w"]


def test_a_count_that_does_not_match_falls_back_and_says_so() -> None:
    from linguexx2odt.equations import equation_targets

    said: list[str] = []
    blocks = [{"t": "Para", "c": [{"t": "Math", "c": [
        {"t": "DisplayMath"}, r"\begin{equation}\label{a} x\end{equation}"]}]}]
    found = equation_targets(blocks, {}, sources=[], warn=said.append)
    assert [e.number for e in found.equations] == ["1"] and len(said) == 1
