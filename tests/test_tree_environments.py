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

"""Tree environments: kept as bracket notation, for the Writer macro to draw.

The converter cannot draw a tree — that needs the draw shapes only Writer
can make.  What it can do is not destroy one: handed to pandoc, a forest
environment came out of the other end as ``]]]``.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from linguexx2odt import postprocess
from linguexx2odt.cli import main
from linguexx2odt.inline import InlineRenderer

pandoc = pytest.mark.skipif(shutil.which("pandoc") is None,
                            reason="pandoc not installed")

TREE_TEX = """\\documentclass[a4paper]{article}
\\usepackage[lazy]{linguexx}
\\begin{document}
\\ex. A normal example.

\\ex. %s
\\end{document}
"""

FOREST = ("\\begin{forest}\n"
          "[CP [DP what] [C' [C did] [TP [V see]]]]\n"
          "\\end{forest}")
QTREE = "\\Tree [.CP [.DP what ] [.C' [.C did ] ] ]"


@pandoc
@pytest.mark.parametrize("source, expected", [
    (FOREST, "[CP [DP what] [C' [C did] [TP [V see]]]]"),
    (QTREE, "[CP [DP what ] [C' [C did ] ] ]"),
])
def test_a_tree_environment_survives_as_bracket_notation(
        tmp_path: Path, source: str, expected: str) -> None:
    """Handed to pandoc, a forest environment came out as "]]]".

    Nothing here can *draw* a tree — that needs the draw shapes only Writer
    can make — but the brackets are what the Writer macro reads, so they
    have to arrive whole and the warning has to say so.  Anything less is
    not the "degrades to readable output" this converter promises.
    """
    tex = tmp_path / "tree.tex"
    tex.write_text(TREE_TEX % source, encoding="utf-8")
    odt = tmp_path / "tree.odt"
    assert main([str(tex), "-o", str(odt), "-q"]) == 0

    content = postprocess.read(odt, "content.xml")
    table = re.findall(r"<table:table .*?</table:table>", content, re.S)[-1]
    text = re.sub(r"<[^>]+>", "", table)
    text = text.replace("&apos;", "'").replace("&amp;", "&")
    assert expected in text, f"the tree did not survive: {text[:80]!r}"
    assert "]]]" not in text.replace(expected, ""), "leftover brackets"


@pandoc
def test_a_tree_environment_warns_and_names_the_command(tmp_path: Path) -> None:
    warnings: list[str] = []
    renderer = InlineRenderer(warn=warnings.append)
    renderer.render(FOREST)
    assert warnings, "a kept-as-text tree said nothing"
    assert "Typeset unnumbered tree" in warnings[0], warnings[0]
