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
r"""References to sections, and to the page of an example (plan-crossrefs.md).

They were deleted, with a warning: "A \ref{s:d} B" came out "A  B".  They
are fields now, as a reference to an example is, and the headings carry
the numbers they show -- an outline numbering, so that moving a section
renumbers the heading and every reference to it.

The expected line is not reasoned out: it is what LaTeX prints for SOURCE
(article, hyperref, cleveref), read off ``pdflatex`` and ``pdftotext``.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from linguexx2odt import postprocess
from linguexx2odt.cli import main
from linguexx2odt.sections import section_table

pandoc = pytest.mark.skipif(shutil.which("pandoc") is None,
                            reason="pandoc not installed")
soffice = pytest.mark.skipif(shutil.which("soffice") is None
                             or shutil.which("pdftotext") is None,
                             reason="libreoffice or pdftotext not installed")

SOURCE = r"""\documentclass{article}
\usepackage{linguexx}
\usepackage{hyperref}
\usepackage{cleveref}
\begin{document}
\section{Intro}\label{s:i}
\ex.\label{e1} An example.

\subsection{Detail}\label{s:d}
\subsubsection{Deep}\label{s:dd}
\section*{Star}\label{s:star}
\section{Two}\label{s:t}
REFS: A \ref{s:d} B \cref{s:dd} C \Cref{s:t} D \autoref{s:d}
E \nameref{s:i} F \pageref{s:t} G \cpageref{e1} H \ref{e1}.
\end{document}
"""

#: LaTeX's rendering of SOURCE.
LATEX = "REFS: A 1.1 B section 1.1.1 C Section 2 D subsection 1.1 E Intro F 1 G page 1 H (1)."

#: What a reader that never updates a field shows (OnlyOffice, for a
#: .docx): the cache.  Right for everything but a page, which cannot be
#: known before layout and says so rather than guess.
CACHED = "REFS: A 1.1 B section 1.1.1 C Section 2 D subsection 1.1 E Intro F ? G page ? H (1)."


def _convert(tmp_path: Path, target: str, quiet: bool = True) -> Path:
    tex = tmp_path / "doc.tex"
    tex.write_text(SOURCE, encoding="utf-8")
    out = tmp_path / f"doc.{target}"
    args = [str(tex), "-o", str(out), "--to", target] + (["-q"] if quiet else [])
    assert main(args) == 0
    return out


def _laid_out(doc: Path) -> str:
    """The document as LibreOffice lays it out: through a PDF, since the
    text export does no layout and so knows no page."""
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf",
                    "--outdir", str(doc.parent), str(doc)],
                   check=True, capture_output=True, timeout=120)
    pdf = doc.with_suffix(".pdf")
    txt = subprocess.run(["pdftotext", str(pdf), "-"], check=True,
                         capture_output=True, text=True).stdout
    return " ".join(txt.split())


def test_sections_are_numbered_as_latex_numbers_them() -> None:
    r"""A \section* takes no number and steps nothing; a \ref to it, or to
    a \paragraph, prints the last number set before it."""
    blocks = [
        {"t": "Header", "c": [1, ["a", [], []], [{"t": "Str", "c": "A"}]]},
        {"t": "Header", "c": [2, ["b", [], []], [{"t": "Str", "c": "B"}]]},
        {"t": "Header", "c": [3, ["c", [], []], [{"t": "Str", "c": "C"}]]},
        {"t": "Header", "c": [1, ["star", ["unnumbered"], []], [{"t": "Str", "c": "S"}]]},
        {"t": "Header", "c": [1, ["d", [], []], [{"t": "Str", "c": "D"}]]},
        {"t": "Header", "c": [4, ["p", [], []], [{"t": "Str", "c": "P"}]]},
        {"t": "Div", "c": [["", [], []], [
            {"t": "Header", "c": [2, ["e", [], []], [{"t": "Str", "c": "E"}]]}]]},
    ]
    table = section_table(blocks)
    assert {k: (s.number, s.shown) for k, s in table.items()} == {
        "a": ("1", "1"), "b": ("1.1", "1.1"), "c": ("1.1.1", "1.1.1"),
        "star": (None, "1.1.1"), "d": ("2", "2"), "p": (None, "2"),
        "e": ("2.1", "2.1"),
    }
    assert table["star"].bookmark.startswith("_Reflxnon")
    assert table["d"].bookmark.startswith("_Reflxsec")


@pandoc
@soffice
@pytest.mark.parametrize("target", ["odt", "docx"])
def test_a_reference_to_a_section_prints_what_latex_prints(
        tmp_path: Path, target: str) -> None:
    text = _laid_out(_convert(tmp_path, target))
    assert LATEX in text, text
    # the headings carry the numbers, and the starred one none
    for heading in ("1 Intro", "1.1 Detail", "1.1.1 Deep", "2 Two"):
        assert heading in text, f"{heading!r} not in:\n{text}"
    assert "Star" in text and not re.search(r"\d Star", text), text


@pandoc
def test_a_docx_caches_what_latex_prints(tmp_path: Path) -> None:
    xml = postprocess.read(_convert(tmp_path, "docx"), "word/document.xml")
    para = next(p for p in re.findall(r"<w:p\b.*?</w:p>", xml, re.S) if "REFS" in p)
    shown = "".join(re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", para))
    assert " ".join(shown.replace(" ", " ").split()) == CACHED


@pandoc
@pytest.mark.parametrize("target", ["odt", "docx"])
def test_a_reference_to_a_section_is_a_field(tmp_path: Path, target: str) -> None:
    out = _convert(tmp_path, target)
    if target == "odt":
        xml = postprocess.read(out, "content.xml")
        assert xml.count("<text:bookmark-ref ") == 6, xml
        assert xml.count('<text:sequence-ref text:reference-format="page"') == 1
    else:
        xml = postprocess.read(out, "word/document.xml")
        assert len(re.findall(r" REF _Reflx\w+ ", xml)) == 5, xml
        assert len(re.findall(r" PAGEREF \w+ ", xml)) == 2, xml


@pandoc
def test_a_reference_to_a_section_is_no_warning(tmp_path: Path, capsys) -> None:
    _convert(tmp_path, "odt", quiet=False)
    err = capsys.readouterr().err
    assert "deleted from the output" not in err, err
