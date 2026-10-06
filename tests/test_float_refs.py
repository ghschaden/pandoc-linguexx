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
r"""References to tables, figures and footnotes (plan-crossrefs.md, step 2).

They were deleted, with a warning, and the captions they would point at had
no number: pandoc writes "A table." where LaTeX writes "Table 1: A table.".
The captions are numbered by live sequences now, one for tables and one for
figures, and a reference is a field on that number -- or on the footnote's
mark, for a note.

The expected text is not reasoned out: it is what LaTeX prints for SOURCE
(article, hyperref, cleveref), read off ``pdflatex`` and ``pdftotext``.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from linguexx2odt import postprocess
from linguexx2odt.cli import main

ROOT = Path(__file__).resolve().parent.parent

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
Text.\footnote{A note.\label{fn:a}} More.\footnote{Second.\label{fn:b}}

\begin{table}[h]
\centering
\begin{tabular}{ll} a & b \\ \end{tabular}
\caption{A table.}\label{tab:a}
\end{table}

\begin{figure}[h]
\centering
\rule{1cm}{1cm}
\caption{A figure.}\label{fig:a}
\end{figure}

\begin{table}[h]
\caption{Second table.}\label{tab:b}
\begin{tabular}{l} c \\ \end{tabular}
\end{table}

REFS: A \ref{fn:b} B \cref{fn:a} C \ref{tab:b} D \cref{tab:a} E \Cref{fig:a}
F \autoref{tab:b} G \autoref{fig:a} H \nameref{tab:a} I \pageref{tab:b}
J \autoref{fn:a}.
MORE: A \cref{fig:a} B \Cref{fn:a} C \nameref{fig:a} D \nameref{fn:a}
E \cpageref{tab:a} F \Cref{tab:a} G \cref{fn:b}.
\end{document}
"""

#: LaTeX's rendering of SOURCE.  \nameref to a footnote prints nothing.
LATEX = [
    "Table 1: A table.",
    "Figure 1: A figure.",
    "Table 2: Second table.",
    "REFS: A 2 B footnote 1 C 2 D table 1 E Figure 1 F Table 2 G Figure 1"
    " H A table I 1 J footnote 1.",
    "MORE: A fig. 1 B Footnote 1 C A figure D E page 1 F Table 1 G footnote 2.",
]

#: What a .docx reader that never updates a field shows: the cache, which is
#: LaTeX's, pages included (pages.py).
CACHED = LATEX


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
def test_captions_and_references_print_what_latex_prints(
        tmp_path: Path, target: str) -> None:
    text = _laid_out(_convert(tmp_path, target))
    for line in LATEX:
        assert line in text, f"{line!r} not in:\n{text}"


@pandoc
@soffice
def test_a_docx_caches_what_latex_prints(tmp_path: Path) -> None:
    xml = postprocess.read(_convert(tmp_path, "docx"), "word/document.xml")
    paras = [" ".join("".join(re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", p))
                      .replace(" ", " ").split())
             for p in re.findall(r"<w:p\b.*?</w:p>", xml, re.S)]
    for line in CACHED:
        assert any(line in p for p in paras), f"{line!r} not in:\n{paras}"


@pandoc
def test_a_reference_to_a_note_names_the_note(tmp_path: Path) -> None:
    """ODF points a note reference at the note's id, which pandoc chose;
    every one must name a note that exists."""
    xml = postprocess.read(_convert(tmp_path, "odt"), "content.xml")
    notes = set(re.findall(r'<text:note\b[^>]*\btext:id="([^"]+)"', xml))
    refs = re.findall(r'<text:note-ref\b[^>]*\btext:ref-name="([^"]*)"', xml)
    assert len(refs) == 5 and set(refs) <= notes and len(notes) == 2, (refs, notes)


@pandoc
def test_a_docx_note_reference_has_its_mark(tmp_path: Path) -> None:
    """NOTEREF needs a bookmark around the mark in the text, which pandoc
    does not make: one per labelled note, each holding its mark."""
    xml = postprocess.read(_convert(tmp_path, "docx"), "word/document.xml")
    names = set(re.findall(r" NOTEREF (\w+) ", xml))
    assert len(names) == 2, names
    for name in names:
        m = re.search(rf'w:name="{name}"/>(.*?)<w:bookmarkEnd', xml, re.S)
        assert m and "<w:footnoteReference" in m.group(1), name


@pandoc
@pytest.mark.skipif(not (ROOT / ".ooxml-schemas" / "wml.xsd").is_file(),
                    reason="run `make schemas` to fetch the ECMA-376 schemas")
def test_the_docx_is_schema_valid(tmp_path: Path) -> None:
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "validate_docx.py"),
                        str(_convert(tmp_path, "docx"))], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


@pandoc
def test_a_reference_to_a_float_or_note_is_no_warning(tmp_path: Path, capsys) -> None:
    _convert(tmp_path, "odt", quiet=False)
    err = capsys.readouterr().err
    assert "deleted from the output" not in err, err


def test_a_tables_label_on_a_div_around_it_is_its_label() -> None:
    r"""pandoc 3.6 puts a table's \label on a Div wrapping it; 3.10 on the
    table.  Either way \ref{t1} must find table 1."""
    from linguexx2odt.sections import targets

    table = {"t": "Table", "c": [["", [], []], [None, [{"t": "Plain", "c": [
        {"t": "Str", "c": "T."}]}]], [], [["", [], []], []], [], [["", [], []], []]]}
    found = targets([{"t": "Div", "c": [["t1", [], []], [table]]}]).by_label()
    assert found["t1"].kind == "table" and found["t1"].number == 1
