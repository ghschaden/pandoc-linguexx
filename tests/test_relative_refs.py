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
r"""``\Next`` and ``\Last``: resolved by position, not left on the floor.

These were listed as a documented limitation whose warning said "pandoc
renders it literally".  It does not.  ``+raw_tex`` keeps ``\Next`` as a
``RawInline "latex"`` and both writers drop one, so

    structures like \Next, involving \textsc{habere}

came out as "structures like , involving HABERE" -- the reference gone and
the comma left behind.  26 times in one paper, in running prose, with
nothing on the page to show something was missing.

The converter can resolve these even though linguexx cannot: linguexx meets
``\Next`` before the next example exists and will only link to an anchor a
previous run recorded, whereas the whole document is parsed here before a
byte is emitted.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from linguexx2odt import postprocess
from linguexx2odt.cli import main
from linguexx2odt.extract import parse

pandoc = pytest.mark.skipif(shutil.which("pandoc") is None,
                            reason="pandoc not installed")

DOC = """\\documentclass[a4paper]{article}
\\usepackage{linguexx}
\\begin{document}
Structures like \\Next, involving HABERE:

\\ex. First example.

\\ex. Second example.

As we saw in \\Last, and earlier in \\LLast. Two ahead is \\NNext, bare \\pLast.

\\ex. Third example.

\\ex. Fourth example.
\\end{document}
"""


def _targets(src: str) -> list[int]:
    """Which example index each relative reference resolved to, in order."""
    result = parse(src)
    rel = {k: v for k, v in result.labels.items() if k.startswith("lx-relative-")}
    return [rel[k][0] for k in sorted(rel, key=lambda s: int(s.rsplit("-", 1)[1]))]


def test_each_relative_points_at_the_right_example() -> None:
    r"""\Next=(1) \Last=(2) \LLast=(1) \NNext=(4) \pLast=(2), 0-based here.

    Written out one by one rather than as a count: an off-by-one in either
    direction is exactly the bug this can have, and a test that only counted
    them would pass through it.
    """
    assert _targets(DOC) == [0, 1, 0, 3, 1]


def test_a_relative_that_points_off_the_end_is_left_alone() -> None:
    """No example after it, so there is nothing to point at.

    It must warn and leave the source as written rather than resolve to
    something arbitrary -- a wrong number is worse than a visible one.
    """
    src = ("\\documentclass{article}\n\\usepackage{linguexx}\n"
           "\\begin{document}\n\\ex. Only one.\n\nSee \\Next.\n\\end{document}\n")
    result = parse(src)
    assert _targets(src) == []
    assert any("points past" in w for w in result.warnings), result.warnings
    assert "\\Next" in result.residue


def test_no_relative_reference_warning_survives() -> None:
    r"""The old warning said pandoc renders these literally.  It did not, and
    a warning the output contradicts is worse than no warning at all."""
    result = parse(DOC)
    assert not [w for w in result.warnings if "relative reference" in w], \
        result.warnings


@pandoc
@pytest.mark.parametrize("target", ["odt", "docx"])
def test_the_reference_reaches_both_targets(tmp_path: Path, target: str) -> None:
    """Rewritten to \\ref, so it takes the path an author's own \\ref takes.

    That is why this needs nothing from either emitter -- and the test is
    parametrised over both to keep it that way.
    """
    tex = tmp_path / "rel.tex"
    tex.write_text(DOC, encoding="utf-8")
    out = tmp_path / f"rel.{target}"
    assert main([str(tex), "-o", str(out), "--to", target, "-q"]) == 0

    member = "content.xml" if target == "odt" else "word/document.xml"
    body = postprocess.read(out, member)
    assert "lx-relative-" not in body, "a synthetic label leaked into the output"
    marker = "text:sequence-ref" if target == "odt" else "REF "
    assert body.count(marker) >= 5, f"expected 5 references, got {body.count(marker)}"


@pandoc
def test_the_prose_reads_correctly(tmp_path: Path) -> None:
    """The hole in the sentence is the whole point; look at the text.

    ``libreoffice --convert-to pdf`` resolves the fields, so this asserts on
    what a reader sees rather than on the markup that should produce it.
    """
    soffice = shutil.which("libreoffice") or shutil.which("soffice")
    if soffice is None:
        pytest.skip("libreoffice not installed")
    import subprocess

    tex = tmp_path / "rel.tex"
    tex.write_text(DOC, encoding="utf-8")
    odt = tmp_path / "rel.odt"
    assert main([str(tex), "-o", str(odt), "-q"]) == 0

    subprocess.run([soffice, "--headless", "--convert-to", "pdf",
                    str(odt), "--outdir", str(tmp_path)],
                   check=True, capture_output=True, timeout=300)
    text = subprocess.run(["pdftotext", "-layout", str(tmp_path / "rel.pdf"), "-"],
                          check=True, capture_output=True, text=True).stdout
    text = " ".join(text.split())
    assert "Structures like (1), involving" in text, text[:200]
    assert "As we saw in (2), and earlier in (1)." in text, text[:300]
    assert "Two ahead is (4), bare 2." in text, text[:300]


def test_a_relative_inside_an_example_is_not_rewritten() -> None:
    r"""Only prose is scanned; an example body is consumed whole.

    Worth pinning: the scan skips example bodies, so a \Next in a
    translation is not seen here at all, and if that ever changes the
    numbering would shift under it.
    """
    src = ("\\documentclass{article}\n\\usepackage{linguexx}\n"
           "\\begin{document}\n\\ex. See \\Next.\n\n\\ex. Second.\n"
           "\\end{document}\n")
    assert _targets(src) == []


def _example_count(odt: Path) -> int:
    content = postprocess.read(odt, "content.xml")
    return len(re.findall(r"<table:table ", content))


@pandoc
def test_rewriting_does_not_disturb_the_examples(tmp_path: Path) -> None:
    """The inline rewrite shares the residue builder with the placeholders.

    A blank line around an inline replacement would split the sentence; a
    missing one around a placeholder would stop it being its own Para and
    lose the example. Both spans go through one sorted pass, so check the
    examples still arrive.
    """
    tex = tmp_path / "rel.tex"
    tex.write_text(DOC, encoding="utf-8")
    odt = tmp_path / "rel.odt"
    assert main([str(tex), "-o", str(odt), "-q"]) == 0
    assert _example_count(odt) == 4
