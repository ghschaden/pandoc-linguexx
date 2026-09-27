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
r"""The document's own macros, inside an example.

Pandoc applies a ``\newcommand`` in the prose, but an example's text is
rendered by this converter, which knew none of them: "An example in
\lang." came out "An example in ." in the .odt, the fragment having gone
to pandoc without the definition, and "An example in \lang." in the
.docx.  The expected text is what linguexx 1.3.2 prints for DOC (pdflatex,
pdftotext), not what seemed right.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from linguexx2odt import postprocess
from linguexx2odt.cli import main
from linguexx2odt.extract import parse

pandoc = pytest.mark.skipif(shutil.which("pandoc") is None,
                            reason="pandoc not installed")
soffice = pytest.mark.skipif(shutil.which("soffice") is None,
                             reason="libreoffice not installed")

DOC = r"""\documentclass{article}
\usepackage{linguexx}
\newcommand{\lang}{Latin}
\newcommand\glo[1]{\lpzg{#1}}
\newcommand{\pair}[2][x]{#1/#2}
\def\br#1{[#1]}
\newcommand*{\nothing}{}
\input{shared}
\begin{document}
Prose: \lang{} and \pair{b}.

\ex. In \lang, \pair{b}, \pair[a]{b}, \br{c}\nothing, \auth.

\exg. puer dorm-it\\
boy sleep-\glo{3sg}\\
\glt `The boy sleeps' (\lang).

\end{document}
"""
SHARED = "\\newcommand{\\auth}{Caesar}\n"

#: linguexx 1.3.2's rendering of DOC.
LINGUEXX = [
    "Prose: Latin and x/b.",
    "In Latin, x/b, a/b, [c], Caesar.",
    "sleep-3sg",          # small capitals: compared case-blind, below
    "‘The boy sleeps’ (Latin).",
]


def _convert(tmp_path: Path, target: str) -> Path:
    (tmp_path / "doc.tex").write_text(DOC, encoding="utf-8")
    (tmp_path / "shared.tex").write_text(SHARED, encoding="utf-8")
    out = tmp_path / f"doc.{target}"
    assert main([str(tmp_path / "doc.tex"), "-o", str(out),
                 "--to", target, "-q"]) == 0
    return out


@pandoc
@soffice
@pytest.mark.parametrize("target", ["odt", "docx"])
def test_the_text_is_what_linguexx_prints(tmp_path: Path, target: str) -> None:
    out = _convert(tmp_path, target)
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf",
                    "--outdir", str(tmp_path), str(out)],
                   check=True, capture_output=True, timeout=120)
    text = subprocess.run(["pdftotext", str(out.with_suffix(".pdf")), "-"],
                          check=True, capture_output=True, text=True).stdout
    text = " ".join(text.split())
    for line in LINGUEXX:
        # LibreOffice draws small capitals as reduced capitals, so its PDF
        # reads "3SG" where linguexx's small-caps face reads "3sg"; the same
        # thing on the page, and the markup test below holds the style.
        assert line.casefold() in text.casefold(), f"{line!r} not in:\n{text}"


@pandoc
@pytest.mark.parametrize("target", ["odt", "docx"])
def test_a_macro_s_markup_is_the_markup_it_expands_to(
        tmp_path: Path, target: str) -> None:
    r"""\glo{3sg} is \lpzg{3sg}: small capitals, as a Leipzig gloss."""
    out = _convert(tmp_path, target)
    member = "content.xml" if target == "odt" else "word/document.xml"
    xml = postprocess.read(out, member)
    for name in ("\\lang", "\\glo", "\\pair", "\\br", "\\auth"):
        assert name not in xml, f"{name} reached the page"
    if target == "odt":
        assert '<text:span text:style-name="LxLeipzig">3sg</text:span>' in xml
    else:
        assert ('<w:rStyle w:val="LxLeipzig"/></w:rPr>'
                '<w:t xml:space="preserve">3sg</w:t>') in xml


def test_a_new_command_over_an_existing_one_is_refused_as_latex_refuses_it() -> None:
    r"""linguexx defines \gl, so \newcommand\gl stops LaTeX with "Command
    \gl already defined" and the definition never takes.  So here: a
    \newcommand does not replace a command the renderer knows, and the run
    says so.  \renewcommand is the author asking for it, and is kept."""
    parsed = parse("\\newcommand\\textit[1]{#1}\\renewcommand\\foo{F}\n"
                   "\\begin{document}\n\\ex. A.\n\n\\end{document}")
    assert "textit" not in parsed.macros
    assert "foo" in parsed.macros
    assert any("textit" in w and "already defined" in w
               for w in parsed.warnings), parsed.warnings


@pandoc
def test_a_macro_survives_an_unknown_command_beside_it() -> None:
    r"""The reason the expansion is textual and comes first: the fallback
    for an unknown command -- pandoc, for the .odt -- is then handed
    "Latin", not a \lang it has no definition for."""
    from linguexx2odt.inline import InlineRenderer
    from linguexx2odt.macros import Macro
    renderer = InlineRenderer()
    renderer.macros = {"lang": Macro(body="Latin")}
    for text in (renderer.render("In \\lang, \\unknowncommand{x}."),
                 renderer.plain("In \\lang, \\unknowncommand{x}.")):
        assert "Latin" in text and "\\lang" not in text, text
