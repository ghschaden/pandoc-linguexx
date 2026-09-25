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
r"""Inline commands a real paper used that the renderer did not know.

All of these came from one NLLT submission.  The interesting one is
``\small``: an unhandled command does not degrade only itself, it sends its
whole enclosing group to pandoc as a fragment, and pandoc does not know
``forest`` either.  So ``{\small \begin{forest}...}`` came back as
``] [Voice' ...`` -- the tree with its head bitten off -- while the same
tree without ``\small`` round-tripped perfectly.  One unknown command three
tokens long destroyed the content next to it.
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


def render(source: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    return InlineRenderer(warn=warnings.append).render(source), warnings


@pytest.mark.parametrize("source, expected", [
    (r"\underline{habuisset}",
     '<text:span text:style-name="LxUnderline">habuisset</text:span>'),
    (r"H\textsubscript{2}O",
     'H<text:span text:style-name="LxSubscript">2</text:span>O'),
    (r"x\textsuperscript{2}",
     'x<text:span text:style-name="LxSuperscript">2</text:span>'),
    (r"file\textunderscore name", "file_ name"),
    (r"a\hspace{1pt}b", "ab"),
    (r"a\hspace*{2mm}b", "ab"),
])
def test_command_renders_without_a_warning(source: str, expected: str) -> None:
    out, warnings = render(source)
    assert out == expected
    assert warnings == [], warnings


@pytest.mark.parametrize("switch", ["small", "footnotesize", "Large", "tiny"])
def test_a_size_switch_disappears_and_keeps_its_group(switch: str) -> None:
    r"""A declaration takes no argument; it must not eat the text after it.

    And it absorbs the space that follows, as a control word does -- a
    leading space in a cell is a column that no longer lines up with the one
    above, and the width estimator measures the string it is given.
    """
    out, warnings = render("{\\%s some text}" % switch)
    assert out == "some text", repr(out)
    assert warnings == [], warnings


def test_underline_is_the_word_the_example_is_about() -> None:
    """28 of the paper's examples underline the form under discussion.

    Rendered as plain text it is still readable, which is why this went
    unnoticed -- but the reader can no longer tell which word is the point
    of the example.
    """
    out, _ = render(r"quodsi \underline{habuisset} facultatem")
    assert "LxUnderline" in out
    assert ">habuisset<" in out


TREE = """\\documentclass[a4paper]{article}
\\usepackage{linguexx}
\\begin{document}
\\ex. {\\small \\begin{forest}
[VoiceP [DP [petitio] ] [Voice' [vP hab- ] ] ]
\\end{forest}}

\\ex. \\begin{forest}
[VoiceP [DP [petitio] ] [Voice' [vP hab- ] ] ]
\\end{forest}
\\end{document}
"""


@pandoc
def test_a_size_switch_does_not_destroy_the_tree_inside_it(
        tmp_path: Path) -> None:
    r"""The two examples differ only by ``{\small ...}``, so they must agree.

    Before this, the first came out ``] [Voice' [vP hab- ] ] ]`` and the
    second came out whole.  Asserting they are EQUAL is what makes the test
    about the switch rather than about any one tree: it cannot pass by both
    being broken the same way, because the second one is the control and is
    checked against the source.
    """
    tex = tmp_path / "tree.tex"
    tex.write_text(TREE, encoding="utf-8")
    odt = tmp_path / "tree.odt"
    assert main([str(tex), "-o", str(odt), "-q"]) == 0

    content = postprocess.read(odt, "content.xml")
    texts = []
    for table in re.findall(r"<table:table .*?</table:table>", content, re.S):
        text = re.sub(r"<[^>]+>", " ", table)
        text = text.replace("&apos;", "'").replace("&amp;", "&")
        texts.append(" ".join(text.split()))
    assert len(texts) == 2, texts

    bracket = "[VoiceP [DP [petitio] ] [Voice' [vP hab- ] ] ]"
    assert bracket in texts[1], f"control tree is wrong: {texts[1]!r}"
    assert bracket in texts[0], f"\\small ate the tree: {texts[0]!r}"
