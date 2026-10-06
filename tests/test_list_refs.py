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
r"""Lists numbered as LaTeX numbers them, and references to their items
(plan-crossrefs.md, step 3).

Pandoc's lists were not LaTeX's: the .odt numbered every level "1.", the
.docx "a." and "i." where article has "(a)" and "i.", and the .odt lost a
list's start number -- \setcounter{enumi}{4} printed "1.".  A reference to
an item was deleted, with a warning.

The expected text is not reasoned out: it is what LaTeX prints for SOURCE,
read off ``pdflatex`` and ``pdftotext``, with one difference, which
sections.Item explains: a second-level item's reference keeps its
parentheses, "2(b)" where LaTeX prints "2b".
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
\usepackage{linguexx}
\usepackage{hyperref}
\usepackage{cleveref}
\begin{document}
\section{Intro}
\begin{enumerate}
\item First.\label{it:a}
\item Second.
  \begin{enumerate}
  \item Inner a.
  \item Inner b.\label{it:bb}
    \begin{enumerate}
    \item Deep.\label{it:deep}
    \end{enumerate}
  \end{enumerate}
\item Third.\label{it:c}
\end{enumerate}
\begin{enumerate}
\setcounter{enumi}{4}
\item Fifth.\label{it:e}
\end{enumerate}

REFS: A \ref{it:a} B \ref{it:bb} C \cref{it:c} D \Cref{it:bb} E \autoref{it:a}
F \nameref{it:a} G \pageref{it:c} H \ref{it:deep} I \ref{it:e}.
\end{document}
"""

#: LaTeX's rendering of SOURCE's lists.
LISTS = ["1. First.", "2. Second.", "(a) Inner a.", "(b) Inner b.", "i. Deep.",
         "3. Third.", "5. Fifth."]

#: LaTeX prints "REFS: A 1 B 2b C item 3 D Item 2b E item 1 F Intro G 1
#: H 2(b)i I 5."; the converter keeps the second level's parentheses.
REFS = "REFS: A 1 B 2(b) C item 3 D Item 2(b) E item 1 F Intro G 1 H 2(b)i I 5."
CACHED = REFS


def _convert(tmp_path: Path, target: str, quiet: bool = True) -> Path:
    tex = tmp_path / "doc.tex"
    tex.write_text(SOURCE, encoding="utf-8")
    out = tmp_path / f"doc.{target}"
    args = [str(tex), "-o", str(out), "--to", target] + (["-q"] if quiet else [])
    assert main(args) == 0
    return out


def _laid_out(doc: Path) -> str:
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf",
                    "--outdir", str(doc.parent), str(doc)],
                   check=True, capture_output=True, timeout=120)
    txt = subprocess.run(["pdftotext", str(doc.with_suffix(".pdf")), "-"],
                         check=True, capture_output=True, text=True).stdout
    return " ".join(txt.split())


@pandoc
@soffice
@pytest.mark.parametrize("target", ["odt", "docx"])
def test_lists_are_numbered_as_latex_numbers_them(tmp_path: Path, target: str) -> None:
    text = _laid_out(_convert(tmp_path, target))
    for line in LISTS:
        assert line in text, f"{line!r} not in:\n{text}"


@pandoc
@soffice
@pytest.mark.parametrize("target", ["odt", "docx"])
def test_a_reference_to_an_item_is_live(tmp_path: Path, target: str) -> None:
    text = _laid_out(_convert(tmp_path, target))
    assert REFS in text, text


@pandoc
@soffice
def test_a_docx_caches_what_the_field_shows(tmp_path: Path) -> None:
    xml = postprocess.read(_convert(tmp_path, "docx"), "word/document.xml")
    para = next(p for p in re.findall(r"<w:p\b.*?</w:p>", xml, re.S) if "REFS" in p)
    shown = "".join(re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", para))
    assert " ".join(shown.replace(" ", " ").split()) == CACHED


@pandoc
def test_a_reference_to_an_item_is_no_warning(tmp_path: Path, capsys) -> None:
    _convert(tmp_path, "odt", quiet=False)
    err = capsys.readouterr().err
    assert "deleted from the output" not in err, err


def test_a_list_starts_where_odf_reads_it() -> None:
    from linguexx2odt.headings import start_odt_lists

    xml = ('<text:list text:style-name="L1" text:start-value="5">\n'
           '  <text:list-item><text:p>x</text:p></text:list-item></text:list>')
    assert start_odt_lists(xml) == (
        '<text:list text:style-name="L1">\n'
        '  <text:list-item text:start-value="5"><text:p>x</text:p></text:list-item></text:list>')


@pandoc
def test_a_list_with_its_own_style_keeps_it_and_its_cache_follows(tmp_path: Path) -> None:
    r"""The enumerate package's [(i)] reaches pandoc as a style of its own,
    which is kept; the cache must be that style's "(ii)", not article's
    "2" -- what the field shows once updated.  LaTeX prints "ii"."""
    tex = tmp_path / "doc.tex"
    tex.write_text("\\documentclass{article}\\usepackage{enumerate}\n"
                   "\\usepackage{linguexx}\\begin{document}\n"
                   "\\begin{enumerate}[(i)]\\item a\\item b\\label{r:b}\\end{enumerate}\n\n"
                   "ROMAN: \\ref{r:b}.\n\\end{document}\n", encoding="utf-8")
    out = tmp_path / "doc.docx"
    assert main([str(tex), "-o", str(out), "--to", "docx", "-q"]) == 0
    xml = postprocess.read(out, "word/document.xml")
    para = next(p for p in re.findall(r"<w:p\b.*?</w:p>", xml, re.S) if "ROMAN" in p)
    assert "".join(re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", para)) == "ROMAN: (ii)."
    assert 'w:val="lowerRoman"' in postprocess.read(out, "word/numbering.xml")


@pandoc
def test_a_label_in_a_footnote_in_an_item_is_the_notes(tmp_path: Path) -> None:
    r"""\cref to it said "item 2": the item took the note's \label.  LaTeX
    prints "footnote 1" (measured)."""
    tex = tmp_path / "doc.tex"
    tex.write_text("\\documentclass{article}\\usepackage{linguexx}\\usepackage{cleveref}\n"
                   "\\begin{document}\n\\begin{enumerate}\n\\item One.\\label{it:one}\n"
                   "\\item Two.\\footnote{A note.\\label{fn:one}}\n\\end{enumerate}\n\n"
                   "NOTE: \\cref{it:one} and \\cref{fn:one}.\n\\end{document}\n", encoding="utf-8")
    out = tmp_path / "doc.docx"
    assert main([str(tex), "-o", str(out), "--to", "docx", "-q"]) == 0
    xml = postprocess.read(out, "word/document.xml")
    para = next(p for p in re.findall(r"<w:p\b.*?</w:p>", xml, re.S) if "NOTE:" in p)
    shown = " ".join("".join(re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", para))
                     .replace("\u00a0", " ").split())
    assert shown == "NOTE: item 1 and footnote 1.", shown
