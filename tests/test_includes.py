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
r"""A document split into files: ``\input`` and ``\include``.

Two losses, both silent, both exit 0.  The reader runs with ``+raw_tex``,
under which pandoc 3.10 does not open ``\input{ch1}`` at all: it keeps it
as a ``RawInline "latex"``, the writer drops that, and a chapter's prose
vanished whole.  And the example scanner read only the main file, so an
example in a chapter would never have become a field even had pandoc read
it.  Both are ended by expanding the files into the source before either
of them looks at it.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from linguexx2odt import postprocess
from linguexx2odt.cli import main
from linguexx2odt.includes import expand_includes

pandoc = pytest.mark.skipif(shutil.which("pandoc") is None,
                            reason="pandoc not installed")


def _expand(tmp_path: Path, src: str, files: dict[str, str]):
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    warnings: list[str] = []
    return expand_includes(src, tmp_path, warnings.append).text, warnings


# -- the expansion ---------------------------------------------------------

def test_input_with_and_without_extension(tmp_path: Path) -> None:
    out, warnings = _expand(tmp_path, "A \\input{one} B \\input{two.tex} C",
                            {"one.tex": "ONE\n", "two.tex": "TWO\n"})
    assert out == "A ONE\n B TWO\n C"
    assert warnings == []


def test_input_prefers_the_tex_file_as_latex_does(tmp_path: Path) -> None:
    out, _ = _expand(tmp_path, "\\input{one}",
                     {"one": "BARE\n", "one.tex": "TEX\n"})
    assert out == "TEX\n"


def test_the_primitive_form_without_braces(tmp_path: Path) -> None:
    out, _ = _expand(tmp_path, "\\input one\nafter", {"one.tex": "ONE\n"})
    assert out == "ONE\n\nafter"


def test_include_starts_a_paragraph(tmp_path: Path) -> None:
    out, _ = _expand(tmp_path, "A\\include{ch}B", {"ch.tex": "CH"})
    assert out == "A\n\nCH\n\nB"


def test_paths_are_relative_to_the_main_document(tmp_path: Path) -> None:
    """As in LaTeX: a file input from a subdirectory names its own inputs
    from the job's directory, not from where it sits."""
    out, _ = _expand(tmp_path, "\\input{chapters/one}", {
        "chapters/one.tex": "one \\input{chapters/two}",
        "chapters/two.tex": "two",
    })
    assert out == "one two\n"


def test_comments_verbatim_and_lookalikes_are_left_alone(tmp_path: Path) -> None:
    src = ("% \\input{one}\n"
           "\\verb|\\input{one}|\n"
           "\\includegraphics{one} \\inputencoding{utf8}\n"
           "\\\\input{one}\n")
    out, warnings = _expand(tmp_path, src, {"one.tex": "ONE"})
    assert out == src
    assert warnings == []


def test_a_final_comment_does_not_swallow_the_rest_of_the_line(
        tmp_path: Path) -> None:
    out, _ = _expand(tmp_path, "\\input{one} after",
                     {"one.tex": "ONE % no newline at the end"})
    assert out.endswith("\n after")


def test_endinput_stops_the_file_after_its_line(tmp_path: Path) -> None:
    out, _ = _expand(tmp_path, "\\input{one}",
                     {"one.tex": "kept \\endinput kept too\ndropped\n"})
    assert out == "kept  kept too\n"


def test_a_missing_file_is_named(tmp_path: Path) -> None:
    out, warnings = _expand(tmp_path, "A \\input{nowhere} B", {})
    assert out == "A  B"
    assert len(warnings) == 1 and "nowhere" in warnings[0], warnings


def test_a_cycle_is_broken_and_named(tmp_path: Path) -> None:
    out, warnings = _expand(tmp_path, "\\input{a}",
                            {"a.tex": "a \\input{b}", "b.tex": "b \\input{a}"})
    assert out == "a b \n"
    assert len(warnings) == 1 and "a.tex" in warnings[0], warnings


def test_includeonly_is_obeyed_and_counted(tmp_path: Path) -> None:
    src = "\\includeonly{one}\n\\include{one}\\include{two}"
    out, warnings = _expand(tmp_path, src, {"one.tex": "ONE", "two.tex": "TWO"})
    assert "ONE" in out and "TWO" not in out
    assert len(warnings) == 1 and "includeonly" in warnings[0], warnings


# -- end to end ------------------------------------------------------------

MAIN = """\\documentclass{article}
\\usepackage{linguexx}
\\begin{document}
Introduction.

\\input{ch1}

\\include{chapters/ch2}

Back in the main file, see \\ref{ex:ch2}.
\\end{document}
"""

CH1 = """Prose of chapter one.

\\ex. \\label{ex:ch1} Jean dort.

"""

CH2 = """Prose of chapter two, after (\\ref{ex:ch1}).

\\ex. \\label{ex:ch2} Marie chante.
"""


@pandoc
def test_a_document_in_several_files_is_converted_whole(tmp_path: Path) -> None:
    (tmp_path / "chapters").mkdir()
    (tmp_path / "main.tex").write_text(MAIN, encoding="utf-8")
    (tmp_path / "ch1.tex").write_text(CH1, encoding="utf-8")
    (tmp_path / "chapters" / "ch2.tex").write_text(CH2, encoding="utf-8")
    odt = tmp_path / "main.odt"

    assert main([str(tmp_path / "main.tex"), "-o", str(odt), "-q"]) == 0

    content = postprocess.read(odt, "content.xml")
    text = re.sub(r"<[^>]+>", "", content)
    for prose in ("Introduction.", "Prose of chapter one.",
                  "Prose of chapter two", "Back in the main file"):
        assert prose in text, f"{prose!r} is missing from the output"
    assert content.count("<text:sequence ") == 2, "an example was not numbered"
    assert content.count("<text:sequence-ref ") == 2, "a reference is not a field"


def test_including_the_main_document_is_caught(tmp_path: Path) -> None:
    main_tex = tmp_path / "main.tex"
    main_tex.write_text("M \\input{one}", encoding="utf-8")
    (tmp_path / "one.tex").write_text("one \\input{main}", encoding="utf-8")
    warnings: list[str] = []
    out = expand_includes(main_tex.read_text(encoding="utf-8"), tmp_path,
                          warnings.append, main=main_tex).text
    assert out.count("M ") == 1, out
    assert len(warnings) == 1 and "main.tex" in warnings[0], warnings


def test_a_warning_names_the_file_and_line_it_is_about(tmp_path: Path) -> None:
    """Parse and emit count lines in the spliced text; a line the author
    can find is one in the file they wrote."""
    (tmp_path / "chapters").mkdir()
    (tmp_path / "pre.tex").write_text("p1\np2\np3\n", encoding="utf-8")
    (tmp_path / "chapters" / "ch.tex").write_text("c1\nc2\n", encoding="utf-8")
    src = "m1\n\\input{pre}\nm3\n\\include{chapters/ch}\nm5\n"
    expanded = expand_includes(src, tmp_path, lambda w: None)
    lines = expanded.text.split("\n")

    def at(text: str) -> str:
        return expanded.locate(f"line {lines.index(text) + 1}: x")

    assert at("m1") == "line 1: x"
    assert at("p2") == "pre.tex, line 2: x"
    assert at("m3") == "line 3: x"
    assert at("c2") == "chapters/ch.tex, line 2: x"
    assert at("m5") == "line 5: x"
    assert expanded.locate("no line here") == "no line here"
