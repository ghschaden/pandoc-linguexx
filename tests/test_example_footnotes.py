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
r"""Footnotes inside examples, and references to them (plan-crossrefs.md).

The renderer did not know \footnote.  The .odt fell back to a pandoc run of
its own for the example, whose note took the id "ftn0" a second time, so a
reference to the document's first note found the example's; the .docx
printed "\footnote{In example.}" in the cell.  A \label in the note was
taken for the example's, so a reference to it printed "(1)".  And footnote
numbering skipped the notes in examples: the caches of references to later
notes were one short.

The expected text is what linguexx prints for SOURCE, read off
``pdflatex`` and ``pdftotext``.
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
Prose.\footnote{First.\label{fn:a}}

\ex. Example text.\footnote{In example.\label{fn:ex}}

\ex. \gll Jean dort\\
          John sleeps\\
\glt `John sleeps.'\footnote{In a gloss.\label{fn:gl}}

After.\footnote{Last.\label{fn:d}} See \ref{fn:a}, \ref{fn:ex}, \cref{fn:gl}, \ref{fn:d}.
\end{document}
"""

#: linguexx's rendering of SOURCE: the marks, the references, and each
#: note under its own number.
LATEX = ["(1) Example text.2", "‘John sleeps.’3", "After.4 See 1, 2, footnote 3, 4.",
         "1 First.", "2 In example.", "3 In a gloss.", "4 Last."]


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
    # -layout and line by line: without it, the .odt's note numbers are
    # read as a column of their own, "1 2 3 4 First. In example. ..."
    txt = subprocess.run(["pdftotext", "-layout", str(doc.with_suffix(".pdf")), "-"],
                         check=True, capture_output=True, text=True).stdout
    # the .docx's note number is a line of its own before the note's text
    lines = [" ".join(line.split()) for line in txt.splitlines() if line.strip()]
    return "\n".join(a + " " + b if a.isdigit() else a
                     for a, b in zip(lines, lines[1:] + [""]))


@pandoc
@soffice
@pytest.mark.parametrize("target", ["odt", "docx"])
def test_a_footnote_in_an_example_is_a_footnote(tmp_path: Path, target: str) -> None:
    text = _laid_out(_convert(tmp_path, target))
    for line in LATEX:
        assert line in text, f"{line!r} not in:\n{text}"
    assert "\\footnote" not in text, text


@pandoc
def test_every_odt_note_has_an_id_of_its_own(tmp_path: Path) -> None:
    xml = postprocess.read(_convert(tmp_path, "odt"), "content.xml")
    ids = re.findall(r'<text:note\b[^>]*\btext:id="([^"]+)"', xml)
    assert len(ids) == 4 and len(set(ids)) == 4, ids


@pandoc
def test_docx_notes_are_numbered_in_text_order(tmp_path: Path) -> None:
    """LibreOffice pairs a mark with its note by the ids' order, Word by
    the id: ids that rise with the text satisfy both."""
    out = _convert(tmp_path, "docx")
    marks = re.findall(r'<w:footnoteReference\b[^>]*\bw:id="(\d+)"',
                       postprocess.read(out, "word/document.xml"))
    assert marks == sorted(marks, key=int) and len(set(marks)) == 4, marks
    notes = postprocess.read(out, "word/footnotes.xml")
    for ident, text in zip(marks, ["First.", "In example.", "In a gloss.", "Last."]):
        m = re.search(rf'<w:footnote\b[^>]*\bw:id="{ident}"[^>]*>(.*?)</w:footnote>',
                      notes, re.S)
        assert m and text in m.group(1), (ident, text)


@pandoc
def test_a_label_in_a_note_is_not_the_examples(tmp_path: Path) -> None:
    from linguexx2odt.extract import parse

    parsed = parse(SOURCE)
    assert "fn:ex" not in parsed.labels and "fn:gl" not in parsed.labels, parsed.labels
