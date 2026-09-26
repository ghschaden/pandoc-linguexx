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
r"""`--font`: the face the document is set in, and measured for.

The two have to be the same face or the columns are sized for something the
document does not use, which is the bug that made every long word wrap
before Phase 4. So the tests here come in pairs: the widths change, *and*
the document says which face it is in.
"""

from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

import pytest

from linguexx2odt.cli import main
from linguexx2odt.measure import _ADVANCE, FontNotFound, advances_for
from linguexx2odt.styles import Layout

pandoc = pytest.mark.skipif(shutil.which("pandoc") is None,
                            reason="pandoc not installed")

SOURCE = r"""\documentclass{article}
\usepackage{linguexx}
\begin{document}
\exg. Der ausserordentlich lange Hund bellte laut.\\
the extraordinarily long dog barked loudly\\
\glt `The dog barked.'
\end{document}
"""


def test_times_metric_faces_use_the_built_in_table() -> None:
    """No file is read for the common case.

    Liberation Serif is what the table was measured from and Times New
    Roman is what it targets; Nimbus Roman and Tinos are the same metrics
    again. Measuring them would be work to arrive back where we started.
    """
    for name in ("Times New Roman", "Liberation Serif", "times new roman",
                 "Nimbus Roman", "Tinos"):
        assert advances_for(name) is _ADVANCE, name


def test_another_face_is_measured_from_its_own_file() -> None:
    got = advances_for("DejaVu Sans")
    assert got is not _ADVANCE
    assert got["m"] != _ADVANCE["m"], "DejaVu Sans is not Times-wide"
    assert len(got) > 200, "barely anything was measured"


def test_the_soft_hyphen_keeps_its_rendered_width() -> None:
    r"""The one place a font file and a renderer disagree.

    The built-in table was measured through LibreOffice, so it records what
    is DRAWN: a soft hyphen is invisible unless it falls at a line break, and
    the table says 0. The font declares 0.333. Measure without applying this
    and every column holding a soft hyphen is a third of an em too wide —
    found by comparing the two routes over 217 characters, where it was the
    only disagreement worth more than 0.0022 em.
    """
    assert advances_for("DejaVu Sans")["­"] == 0.0


def test_a_name_no_font_answers_to_is_refused() -> None:
    """fontconfig always answers, so the answer has to be checked.

    Asked for a face it has never heard of it returns its best guess, and
    measuring that would size the columns for a font nobody chose — silently,
    which is the worst way for this to be wrong.
    """
    with pytest.raises(FontNotFound, match="no font named"):
        advances_for("Definitely Not An Installed Typeface 12345")


def test_layout_carries_the_face_through() -> None:
    assert Layout().advances is _ADVANCE
    assert Layout(font_name="DejaVu Sans").advances is not _ADVANCE


@pandoc
def test_docx_declares_the_face_it_was_measured_for(tmp_path: Path) -> None:
    src = tmp_path / "f.tex"
    src.write_text(SOURCE, encoding="utf-8")
    out = tmp_path / "f.docx"
    assert main([str(src), "--to", "docx", "-o", str(out),
                 "--font", "DejaVu Serif", "-q"]) == 0
    styles = zipfile.ZipFile(out).read("word/styles.xml").decode("utf-8")
    default = re.search(r"<w:rPrDefault>.*?</w:rPrDefault>", styles, re.S)
    assert default and 'w:ascii="DejaVu Serif"' in default.group(0)


@pandoc
def test_odt_declares_the_face_and_the_font_face_entry(tmp_path: Path) -> None:
    """ODF needs the face DECLARED as well as named.

    Without an `office:font-face-decls` entry a reader may substitute, and
    LibreOffice did: asked for DejaVu Serif it rendered Liberation Serif,
    which is a good Times substitute and not what the columns were measured
    for. OOXML needs no equivalent.
    """
    src = tmp_path / "g.tex"
    src.write_text(SOURCE, encoding="utf-8")
    out = tmp_path / "g.odt"
    assert main([str(src), "-o", str(out), "--font", "DejaVu Serif", "-q"]) == 0
    styles = zipfile.ZipFile(out).read("styles.xml").decode("utf-8")
    assert 'style:font-name="DejaVu Serif"' in styles, "the face is not named"
    decls = re.search(r"<office:font-face-decls>.*?</office:font-face-decls>",
                      styles, re.S)
    assert decls and "DejaVu Serif" in decls.group(0), (
        "the face is named but never declared, so a reader may substitute")


@pandoc
def test_a_different_face_moves_the_columns(tmp_path: Path) -> None:
    """The point of measuring: wider face, wider columns."""
    src = tmp_path / "w.tex"
    src.write_text(SOURCE, encoding="utf-8")

    def columns(font: str) -> list[int]:
        out = tmp_path / f"{font.replace(' ', '')}.docx"
        assert main([str(src), "--to", "docx", "-o", str(out),
                     "--font", font, "-q"]) == 0
        xml = zipfile.ZipFile(out).read("word/document.xml").decode("utf-8")
        return [int(w) for w in re.findall(r'<w:gridCol w:w="(\d+)"/>', xml)]

    times, dejavu = columns("Times New Roman"), columns("DejaVu Serif")
    assert len(times) == len(dejavu), "the grid changed shape, not just width"
    assert dejavu != times, "the columns did not react to the face at all"

    # Not the TOTAL: the table always spans the text block and the slack
    # goes to the trailing filler, so a wider face buys wider content
    # columns and a narrower filler, and the sum barely moves (9637 against
    # 9640 when this was written).  Compare the content columns.
    assert sum(dejavu[:-1]) > sum(times[:-1]), (
        f"DejaVu Serif is the wider face, but its content columns "
        f"({sum(dejavu[:-1])}) are no wider than Times' ({sum(times[:-1])})")


def test_a_measured_face_needs_no_font_file(monkeypatch) -> None:
    """Aptos -- Word's default since 2023 -- is carried as numbers, so it is
    estimated from its own metrics where it is not installed, which is
    everywhere but Windows and Mac, CI included.  Measured from Microsoft's
    Aptos.ttf by tools/measure_face.py."""
    from linguexx2odt import measure

    def no_file(name):
        raise AssertionError(f"read a font file for {name!r}")

    monkeypatch.setattr(measure, "_font_file", no_file)
    measure.advances_for.cache_clear()
    try:
        aptos = advances_for("Aptos")
        assert aptos is measure._FACE_ADVANCE["aptos"]
        assert advances_for("aptos") is aptos
        # wider than Times, which is why a Times estimate wraps it
        word = "ausserordentlich"
        assert sum(aptos[c] for c in word) > 1.1 * sum(_ADVANCE[c] for c in word)
    finally:
        measure.advances_for.cache_clear()
