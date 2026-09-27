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
r"""References inside an example, and ranges anywhere.

A ``\ref`` inside an example was no reference in either target: the .odt
handed the cell to pandoc and got no field, the .docx printed ``\ref{a}``
as eight characters.  ``\refrange`` was deleted everywhere.  The expected
text below is not reasoned out -- it is what linguexx 1.3.2 prints for
DOC, read off ``TEXINPUTS=../linguexx: pdflatex`` and ``pdftotext``.  Note
the ranges: the second half is a bare sub-letter only when its label is a
``\sublabel`` (``\refrange{a}{s1}`` is "(1--3a)", ``s1`` being a
``\label``), and then even across examples ("1--b").
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from linguexx2odt import postprocess
from linguexx2odt.cli import main

pandoc = pytest.mark.skipif(shutil.which("pandoc") is None,
                            reason="pandoc not installed")
soffice = pytest.mark.skipif(shutil.which("soffice") is None,
                             reason="libreoffice not installed")

DOC = r"""\documentclass{article}
\usepackage{linguexx}
\begin{document}
\ex. \label{a} One.

\ex. See \ref{a} and \pref{a}; Last \Last, Next \Next, pLLast \pLLast.

\ex. \a. \label{s1} Sub a. \b. \sublabel{s2} Sub b. \c. \sublabel{s3} Sub c.

\ex. \gll Jean dort \\ John sleeps \\ \glt `As in \ref{s1}.'

\ex. Ranges \refrange{s1}{s3}, \refrange{s2}{s3}, \prefrange{a}{s2}, \refrange{a}{s1}.

Prose: \refrange{s2}{s3} and \refrange{a}{s1} and \prefrange{a}{s3}.
\end{document}
"""

#: linguexx 1.3.2's rendering of DOC, line by line (pdftotext -layout).
LINGUEXX = [
    "See (1) and 1; Last (2), Next (3), pLLast 1.",
    "‘As in (3a).’",
    "Ranges (3a–c), (3b–c), 1–b, (1–3a).",
    "Prose: (3b–c) and (1–3a) and 1–c.",
]

#: Live fields in DOC: five in example 2, one in 4, five in 5 -- a range
#: is one field, or two when its end is a full reference -- and four in
#: the prose.
FIELDS = 15


def _convert(tmp_path: Path, target: str) -> tuple[Path, str]:
    tex = tmp_path / "refs.tex"
    tex.write_text(DOC, encoding="utf-8")
    out = tmp_path / f"refs.{target}"
    assert main([str(tex), "-o", str(out), "--to", target, "-q"]) == 0
    member = "content.xml" if target == "odt" else "word/document.xml"
    return out, postprocess.read(out, member)


def _text(doc: Path) -> str:
    """The document as LibreOffice reads it, whitespace collapsed."""
    subprocess.run(["soffice", "--headless", "--convert-to", "txt:Text",
                    "--outdir", str(doc.parent), str(doc)],
                   check=True, capture_output=True, timeout=120)
    txt = doc.with_suffix(".txt").read_text(encoding="utf-8-sig")
    return " ".join(txt.split())


@pandoc
@soffice
@pytest.mark.parametrize("target", ["odt", "docx"])
def test_the_text_is_what_linguexx_prints(tmp_path: Path, target: str) -> None:
    out, _ = _convert(tmp_path, target)
    text = _text(out)
    for line in LINGUEXX:
        assert line in text, f"{line!r} not in:\n{text}"


@pandoc
@pytest.mark.parametrize("target", ["odt", "docx"])
def test_every_reference_is_a_field(tmp_path: Path, target: str) -> None:
    _, xml = _convert(tmp_path, target)
    assert "\\ref" not in xml and "\\Next" not in xml, "LaTeX reached the page"
    marker = "<text:sequence-ref " if target == "odt" else " REF NumEx"
    assert xml.count(marker) == FIELDS, xml.count(marker)


@pandoc
def test_a_docx_reference_caches_the_number_it_resolves_to(tmp_path: Path) -> None:
    r"""OnlyOffice shows the cache and does not recalculate (CLAUDE.md), so
    a REF inside an example must carry its right number from the start."""
    _, xml = _convert(tmp_path, "docx")
    cached = re.findall(
        r" REF NumEx(\d+) \\h </w:instrText>.*?"
        r'w:fldCharType="separate"/>.*?<w:t[^>]*>([^<]*)</w:t>', xml, re.S)
    assert len(cached) == FIELDS
    for index, shown in cached:
        assert shown == str(int(index) + 1), (index, shown)


def test_an_unknown_label_is_named_and_marked() -> None:
    r"""LaTeX prints ?? for a label it cannot resolve; so does this, and
    the run says which one."""
    from linguexx2odt.emit_base import emitter_for
    from linguexx2odt.extract import parse
    parsed = parse("\\begin{document}\n\\ex. See \\ref{nowhere}.\n\n\\end{document}")
    for target in ("odt", "docx"):
        emitter = emitter_for(target, labels=parsed.labels)
        emitter.prepare(parsed.examples)
        xml = emitter.example(parsed.examples[0])
        assert "(??)" in xml and "\\ref" not in xml, (target, xml)
        assert any("nowhere" in w for w in emitter.warnings), emitter.warnings


def test_a_redefined_range_dash_is_named() -> None:
    r"""The drift CLAUDE.md warns of: a command the converter handles,
    changed in the preamble, with nothing unknown left to warn about."""
    from linguexx2odt.extract import parse
    warnings = parse("\\usepackage{linguexx}\\renewcommand\\rangedash{-}\n"
                     "\\begin{document}\n\\ex. \\label{a} A.\n\n"
                     "See \\refrange{a}{a}.\n\\end{document}").warnings
    assert any("rangedash" in w for w in warnings), warnings


FALLBACK = r"""\documentclass{article}
\usepackage{linguexx}
\begin{document}
\ex. \label{a} One.

\ex. See \ref{a}, \pref{a} and \Last, beside \unknowncommand{x}.

\end{document}
"""


@pandoc
@pytest.mark.parametrize("target", ["odt", "docx"])
def test_a_reference_survives_an_unknown_command_beside_it(
        tmp_path: Path, target: str) -> None:
    r"""One command the renderer does not know sends the whole cell down
    the fallback -- pandoc for the .odt, the source as text for the .docx
    -- and neither knows an example label: the references went with it."""
    tex = tmp_path / "fb.tex"
    tex.write_text(FALLBACK, encoding="utf-8")
    out = tmp_path / f"fb.{target}"
    assert main([str(tex), "-o", str(out), "--to", target, "-q"]) == 0
    member = "content.xml" if target == "odt" else "word/document.xml"
    xml = postprocess.read(out, member)
    marker = "<text:sequence-ref " if target == "odt" else " REF NumEx"
    assert xml.count(marker) == 3, xml.count(marker)
    assert "\\ref" not in xml and "\\Last" not in xml and "lx:ref" not in xml


def test_a_reference_to_a_sub_sub_example_is_named_as_unsupported() -> None:
    r"""linguexx prints "(1b-i)"; this converter prints "(1i)".  Decided
    2026-09-27: cross-references to sub-sub-examples are not implemented --
    but a wrong number is not left unsaid, in prose or in an example, and a
    reference to a sub-example one level up is not warned about."""
    from linguexx2odt.extract import parse
    src = ("\\documentclass{article}\n\\usepackage{linguexx}\n\\begin{document}\n"
           "\\ex. \\a. \\label{la} Letter a.\n"
           "\\b. \\a. \\label{r1} Roman one. \\b. \\sublabel{r2} Roman two.\n\n"
           "\\ex. In an example, \\ref{r2}.\n\n"
           "See \\ref{r1}, \\pref{r2}, \\refrange{r1}{r2} and \\ref{la}.\n"
           "\\end{document}\n")
    warned = [w for w in parse(src).warnings if "sub-sub-example" in w]
    assert {w.split(":")[0] for w in warned} == {"line 7", "line 9"}, warned
    assert any("r1" in w for w in warned) and any("r2" in w for w in warned)
    assert not any("'la'" in w for w in warned), warned
