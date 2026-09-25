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
r"""An example inside an environment pandoc does not know.

A real paper put one inside ``\begin{multicols}{2}``.  Pandoc does not know
that environment, so it handed the whole thing back as a single
``RawBlock "latex"`` -- ``\begin``, the placeholder and ``\end`` together --
and the ODT writer drops a raw LaTeX block.  The example was not degraded,
it was absent: 46 examples in, 45 out.

The run said so, which is the placeholder count doing its job, but a
warning is not a document.  These tests are about the example arriving.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from linguexx2odt import postprocess
from linguexx2odt.cli import main

pandoc = pytest.mark.skipif(shutil.which("pandoc") is None,
                            reason="pandoc not installed")

DOC = """\\documentclass[a4paper]{article}
\\usepackage{linguexx}
\\usepackage{multicol}
\\begin{document}
\\ex. \\label{first}Outside, before.

%s

\\ex. Outside, after: see \\ref{first}.
\\end{document}
"""

WRAPPED = """\\begin{multicols}{2}
\\ex. Trapped in a raw environment.
\\end{multicols}"""

TWO_WRAPPED = """\\begin{multicols}{2}
\\ex. First one trapped.

\\ex. Second one trapped.
\\end{multicols}"""


def _example_texts(odt: Path) -> list[str]:
    """The visible text of every example table, in document order."""
    content = postprocess.read(odt, "content.xml")
    out = []
    for table in re.findall(r"<table:table .*?</table:table>", content, re.S):
        text = re.sub(r"<[^>]+>", " ", table)
        text = text.replace("&apos;", "'").replace("&amp;", "&")
        out.append(" ".join(text.split()))
    return out


@pandoc
def test_an_example_inside_a_raw_environment_reaches_the_output(
        tmp_path: Path) -> None:
    r"""The whole point: 3 examples in, 3 examples out.

    Before this was fixed the run returned 1 and the middle example was
    missing from content.xml entirely -- not mangled, not warned about in
    place, gone.
    """
    tex = tmp_path / "wrapped.tex"
    tex.write_text(DOC % WRAPPED, encoding="utf-8")
    odt = tmp_path / "wrapped.odt"
    assert main([str(tex), "-o", str(odt), "-q"]) == 0, \
        "an example was lost, which is what the exit code is for"

    texts = _example_texts(odt)
    assert len(texts) == 3, f"expected 3 example tables, got {len(texts)}"
    assert "Trapped in a raw environment." in texts[1], texts


@pandoc
def test_the_number_and_the_order_are_the_source_order(tmp_path: Path) -> None:
    """Recovered in place, not appended at the end.

    Splitting the raw block is what keeps the example where the author put
    it; lifting it out to the end of the document would also make the count
    come right, and would renumber the paper.
    """
    tex = tmp_path / "wrapped.tex"
    tex.write_text(DOC % WRAPPED, encoding="utf-8")
    odt = tmp_path / "wrapped.odt"
    assert main([str(tex), "-o", str(odt), "-q"]) == 0

    texts = _example_texts(odt)
    assert "Outside, before." in texts[0], texts
    assert "Trapped in a raw environment." in texts[1], texts
    assert "Outside, after" in texts[2], texts


@pandoc
def test_several_examples_in_one_raw_block_all_arrive(tmp_path: Path) -> None:
    """One raw block can hold more than one placeholder."""
    tex = tmp_path / "two.tex"
    tex.write_text(DOC % TWO_WRAPPED, encoding="utf-8")
    odt = tmp_path / "two.odt"
    assert main([str(tex), "-o", str(odt), "-q"]) == 0

    texts = _example_texts(odt)
    assert len(texts) == 4, f"expected 4 example tables, got {len(texts)}"
    assert "First one trapped." in texts[1], texts
    assert "Second one trapped." in texts[2], texts


@pandoc
def test_recovering_it_warns_and_names_the_environment(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    r"""The surrounding markup really is dropped, so say so.

    ``multicols`` set two columns; the output has one.  The example is back
    but the layout it sat in is not, and that is worth a line -- naming the
    environment is what lets the author decide whether it mattered.
    """
    tex = tmp_path / "wrapped.tex"
    tex.write_text(DOC % WRAPPED, encoding="utf-8")
    odt = tmp_path / "wrapped.odt"
    assert main([str(tex), "-o", str(odt)]) == 0

    err = capsys.readouterr().err
    assert "multicols" in err, err
    assert "kept raw" in err, err
