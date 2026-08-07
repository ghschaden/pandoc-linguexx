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

"""Column widths for text that is not drawn as it is spelled.

``\\lpzg{3sg}`` and ``\\textsc{prs}`` set small capitals, which are the
capitals drawn at ``Layout.sc_ratio`` — wider than the lowercase they
stand in for, for most letters.  Estimating them from the lowercase makes
the column too narrow for its own contents.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from linguexx2odt import postprocess
from linguexx2odt.cli import main
from linguexx2odt.emit_odt import runs_width_cm, text_width_cm
from linguexx2odt.inline import InlineRenderer
from linguexx2odt.styles import Layout

HERE = Path(__file__).resolve().parent
pandoc = pytest.mark.skipif(shutil.which("pandoc") is None,
                            reason="pandoc not installed")

#: Leipzig glosses as they are actually written — lowercase letters that
#: are narrow in lowercase and wider as capitals.
GLOSSES = ["3sg", "prs", "ptcp", "gen", "sg.acc", "def.nom.sg"]


def width(fragment: str) -> float:
    lay = Layout()
    return runs_width_cm(InlineRenderer().runs(fragment), lay.em_cm, lay.sc_ratio)


@pytest.mark.parametrize("style", ["lpzg", "textsc"])
def test_small_caps_are_measured_wider_than_the_lowercase(style: str) -> None:
    """The bug this exists for: measured as lowercase, the column is too
    narrow for the capitals that get drawn in it."""
    lay = Layout()
    for gloss in GLOSSES:
        plain = text_width_cm(gloss, lay.em_cm)
        assert width(f"\\{style}{{{gloss}}}") > plain, (
            f"\\{style}{{{gloss}}} is measured at the width of {gloss!r}"
        )


@pytest.mark.parametrize("style", ["lpzg", "textsc"])
def test_small_caps_are_never_wider_than_full_capitals(style: str) -> None:
    """The other way to be wrong.  A small capital is the capital at
    sc_ratio, so it can never take more room than the capital itself —
    and for a letter already wide in lowercase (m, w) it may take less
    than the lowercase, which is correct and not a sandwich."""
    lay = Layout()
    for gloss in GLOSSES + ["nom", "wm", "MIXEDcase"]:
        caps = text_width_cm(gloss.upper(), lay.em_cm)
        # strictly narrower wherever there is a lowercase letter to shrink:
        # equality would mean sc_ratio had been left at 1
        assert width(f"\\{style}{{{gloss}}}") < caps, (
            f"\\{style}{{{gloss}}} is measured at the full width of "
            f"{gloss.upper()!r} — sc_ratio is not being applied"
        )
    # nothing to shrink: an all-capitals gloss draws at its own width
    assert width(f"\\{style}{{NOM}}") == pytest.approx(
        text_width_cm("NOM", lay.em_cm)
    )


def test_text_with_no_small_caps_measures_exactly_as_before() -> None:
    """The change must not move any column that has no small caps in it."""
    lay = Layout()
    for fragment in ["Beispiel", "the little child", "sleep-", "a.gen", ""]:
        assert width(fragment) == pytest.approx(
            text_width_cm(fragment, lay.em_cm)
        )


def test_runs_marks_only_the_small_caps_part() -> None:
    renderer = InlineRenderer()
    assert renderer.runs("und \\lpzg{3sg} dann") == [
        ("und ", False), ("3sg", True), (" dann", False),
    ]
    # nested inside another font command, the small caps still count
    assert renderer.runs("\\textit{\\textsc{prs}}") == [("prs", True)]
    # and plain() is still exactly the text, so nothing else shifts
    assert renderer.plain("und \\lpzg{3sg} dann") == "und 3sg dann"


TEX = """\\documentclass[a4paper]{article}
\\usepackage[lazy]{linguexx}
\\begin{document}
\\ex. \\gll Aaa bbb ccc \\\\
     xxx %s zzz \\\\
\\glt `A test.'
\\end{document}
"""


def column_widths(odt: Path) -> list[float]:
    content = postprocess.read(odt, "content.xml")
    widths = dict(re.findall(
        r'<style:style style:name="([^"]+)" style:family="table-column">'
        r'<style:table-column-properties style:column-width="([\d.]+)cm"', content))
    return [float(widths[n]) for n in
            re.findall(r'<table:table-column table:style-name="([^"]+)"', content)]


@pandoc
def test_a_leipzig_gloss_widens_its_own_column_only(tmp_path: Path) -> None:
    """End to end: the same example twice, one gloss marked up and one not.

    Exactly one column may differ — the one holding the gloss — and it has
    to be the wider of the two.
    """
    built = {}
    for name, gloss in (("marked", "\\lpzg{prs}"), ("plain", "prs")):
        tex = tmp_path / f"{name}.tex"
        tex.write_text(TEX % gloss, encoding="utf-8")
        odt = tmp_path / f"{name}.odt"
        assert main([str(tex), "-o", str(odt), "-q"]) == 0
        built[name] = column_widths(odt)

    marked, plain = built["marked"], built["plain"]
    assert len(marked) == len(plain), (
        f"the markup changed the grid, not just a width: {marked} / {plain}"
    )
    moved = [i for i, (a, b) in enumerate(zip(marked, plain)) if abs(a - b) > 0.001]
    moved = [i for i in moved if i != len(marked) - 1]      # trailing filler
    assert len(moved) == 1, (
        f"{len(moved)} columns changed width, expected 1: {marked} / {plain}"
    )
    assert marked[moved[0]] > plain[moved[0]], (
        f"the \\lpzg column is {marked[moved[0]]}cm against the lowercase "
        f"{plain[moved[0]]}cm — it was measured as lowercase"
    )
