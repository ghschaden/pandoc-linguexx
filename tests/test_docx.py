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
r"""The .docx target: numbers, references, and what it does not do yet.

Phase 2 of plan-docx.md.  What is claimed here is narrow on purpose — a
plain example and a reference to it — and the tests say where the edge is,
because a target that quietly lays a gloss out wrong is worse than one that
says it cannot.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from linguexx2odt.cli import main

HERE = Path(__file__).parent
ROOT = HERE.parent
SCHEMAS = ROOT / ".ooxml-schemas"

pandoc = pytest.mark.skipif(shutil.which("pandoc") is None,
                            reason="pandoc not installed")

PLAIN = r"""\documentclass{article}
\usepackage{linguexx}
\begin{document}
\ex.\label{one} A first example.

\ex.\label{two} A second example.

Prose referring to \ref{one} and \ref{two}, and bare \pref{one}.
\end{document}
"""


def build(tmp_path: Path, source: str, name: str = "t") -> Path:
    src = tmp_path / f"{name}.tex"
    src.write_text(source, encoding="utf-8")
    out = tmp_path / f"{name}.docx"
    assert main([str(src), "--to", "docx", "-o", str(out), "-q"]) == 0
    return out


def document_xml(docx: Path) -> str:
    return zipfile.ZipFile(docx).read("word/document.xml").decode("utf-8")


def cached_values(docx: Path) -> list[str]:
    """What each field shows to a reader that does not recalculate."""
    return re.findall(r'separate"/></w:r><w:r><w:t>([^<]*)</w:t>',
                      document_xml(docx))


@pandoc
def test_numbers_and_references_are_fields(tmp_path: Path) -> None:
    xml = document_xml(build(tmp_path, PLAIN))
    assert xml.count("SEQ NumEx") == 2, "one SEQ field per example"
    assert xml.count("REF NumEx") == 3, r"\ref, \ref and \pref"
    assert 'w:name="NumEx0"' in xml and 'w:name="NumEx1"' in xml


@pandoc
def test_cached_values_are_correct(tmp_path: Path) -> None:
    """Fact 12, and the reason it is a fact.

    A field carries the text shown by a reader that does not recalculate,
    and readers differ: LibreOffice recalculates on open, OnlyOffice 9.4
    does not and showed (1) (1) with both references reading 99.  So the
    cache is not a hint to be corrected later — it is what somebody sees.
    """
    assert cached_values(build(tmp_path, PLAIN)) == ["1", "2", "1", "2", "1"]


@pandoc
def test_the_bookmark_wraps_the_field_and_not_the_line(tmp_path: Path) -> None:
    r"""Fact 3: otherwise \ref gives back the whole example, not its number."""
    xml = document_xml(build(tmp_path, PLAIN))
    m = re.search(r'<w:bookmarkStart[^>]*w:name="NumEx0"/>(.*?)<w:bookmarkEnd',
                  xml, re.S)
    assert m, "no bookmark around the first number"
    inside = m.group(1)
    assert "SEQ NumEx" in inside, "the bookmark does not contain the field"
    assert "A first example" not in inside, (
        "the bookmark swallowed the example text; a reference to it would "
        "give back the line rather than the number")


@pandoc
def test_a_gloss_says_it_is_not_laid_out_yet(tmp_path: Path, capsys) -> None:
    """Phase 3 is the grid.  Until then this must not fail silently."""
    src = tmp_path / "g.tex"
    src.write_text(r"""\documentclass{article}
\usepackage{linguexx}
\begin{document}
\exg. il mio libro\\
the my book\\
\glt `my book'
\end{document}
""", encoding="utf-8")
    assert main([str(src), "--to", "docx", "-o", str(tmp_path / "g.docx")]) == 0
    assert "cannot lay out a gloss yet" in capsys.readouterr().err


@pandoc
@pytest.mark.skipif(not (SCHEMAS / "wml.xsd").is_file(),
                    reason="run `make schemas` to fetch the ECMA-376 schemas")
def test_the_output_is_schema_valid(tmp_path: Path) -> None:
    """Conformance, which is most of what makes Word refuse a file.

    This one is allowed to skip where the rest of the suite is not: it
    needs an 8 MB download rather than an installed tool, and making every
    contributor fetch a standard to run the tests would be a worse trade.
    `make schemas` once, and it runs from then on.
    """
    docx = build(tmp_path, PLAIN)
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "validate_docx.py"),
                        str(docx)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


@pandoc
@pytest.mark.skipif(shutil.which("soffice") is None, reason="soffice not installed")
def test_it_renders_the_same_as_the_odt_target(tmp_path: Path) -> None:
    """Two targets, one document, one reading.

    The strongest check available without opening Word: whatever the
    markup, the page has to say the same thing.
    """
    def render(path: Path) -> str:
        outdir = tmp_path / (path.suffix[1:] + "-pdf")
        outdir.mkdir(exist_ok=True)
        subprocess.run(["soffice", "--headless", "--convert-to", "pdf",
                        str(path), "--outdir", str(outdir)],
                       capture_output=True, timeout=300)
        pdf = outdir / (path.stem + ".pdf")
        text = subprocess.run(["pdftotext", str(pdf), "-"],
                              capture_output=True, text=True).stdout
        # drop the page number a renderer may add
        return " ".join(text.split())

    docx = build(tmp_path, PLAIN, "both")
    odt = tmp_path / "both.odt"
    src = tmp_path / "both.tex"
    assert main([str(src), "-o", str(odt), "-q"]) == 0

    from_docx, from_odt = render(docx), render(odt)
    expected = ("(1) A first example. (2) A second example. "
                "Prose referring to (1) and (2), and bare 1.")
    assert from_docx.startswith(expected), from_docx
    assert from_odt.startswith(expected), from_odt
