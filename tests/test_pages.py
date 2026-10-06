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
r"""The page a \pageref caches (pages.py).

A page field's cached value is what a reader that never updates fields
shows -- OnlyOffice, for a .docx.  It was "?" always; it is the page
LibreOffice lays the bookmark out on, when LibreOffice is there.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from linguexx2odt import pages, postprocess
from linguexx2odt.cli import main

pandoc = pytest.mark.skipif(shutil.which("pandoc") is None,
                            reason="pandoc not installed")
layout = pytest.mark.skipif(shutil.which("soffice") is None
                            or shutil.which("pdfinfo") is None,
                            reason="libreoffice or pdfinfo not installed")

#: Section B starts on page 2, after sixty paragraphs: "1" would be right by
#: accident for any section.  (Not \newpage, which the converter deletes.)
SOURCE = (r"""\documentclass{article}
\usepackage{linguexx}
\begin{document}
\section{A}\label{s:a}
PAGES: \pageref{s:a} and \pageref{s:b} and \pageref{x}.

\ex.\label{x} An example.

""" + "Filler text for a line.\n\n" * 60 + r"""
\section{B}\label{s:b}
Text.
\end{document}
""")


def _cached(tmp_path: Path, target: str, quiet: bool = True) -> str:
    tex = tmp_path / "doc.tex"
    tex.write_text(SOURCE, encoding="utf-8")
    out = tmp_path / f"doc.{target}"
    assert main([str(tex), "-o", str(out), "--to", target] + (["-q"] if quiet else [])) == 0
    xml = postprocess.read(out, "word/document.xml")
    para = next(p for p in re.findall(r"<w:p\b.*?</w:p>", xml, re.S) if "PAGES" in p)
    return "".join(re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", para))


@pandoc
@layout
def test_a_docx_caches_the_page_libreoffice_lays_it_out_on(tmp_path: Path) -> None:
    """The page of section B in the cache is the one LibreOffice's own PDF
    of the file prints its heading on -- not a number reasoned out."""
    cached = _cached(tmp_path, "docx")
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf",
                    "--outdir", str(tmp_path), str(tmp_path / "doc.docx")],
                   check=True, capture_output=True, timeout=120)
    text = subprocess.run(["pdftotext", str(tmp_path / "doc.pdf"), "-"],
                          check=True, capture_output=True, text=True).stdout
    page_of_b = next(n for n, page in enumerate(text.split("\f"), 1)
                     if re.search(r"^2\s*B$", page, re.M))
    assert page_of_b > 1
    assert cached == f"PAGES: 1 and {page_of_b} and 1."


@pandoc
def test_without_libreoffice_the_cache_says_so(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(pages.shutil, "which", lambda _name: None)
    assert _cached(tmp_path, "docx", quiet=False) == "PAGES: ? and ? and ?."
    assert "needs LibreOffice and pdfinfo" in capsys.readouterr().err
