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
r"""natbib and biblatex citations.

Pandoc's LaTeX reader already understands these: \citet, \citep, \citealt,
\citeauthor, the optional prefix and suffix, several keys at once, all come
back as a Cite with the right mode.  What it cannot do unaided is *say*
anything, because a Cite's text comes from citeproc and a Cite nothing
resolved carries only the RawInline the reader kept -- which both writers
drop.  So 41 citations in a real paper reached the page as 41 empty gaps:
"According to authors like , the Latin construction..." -- and nothing
warned, because as far as the converter was concerned pandoc had it.

Two things are tested here, and the second matters as much as the first: a
citation resolves when there is a bibliography, and it is VISIBLE when there
is not.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from linguexx2odt.cli import main
from linguexx2odt.latexutil import scan_bibliography

pandoc = pytest.mark.skipif(shutil.which("pandoc") is None,
                            reason="pandoc not installed")

BIB = """\
@incollection{vincent1982,
  author = {Vincent, Nigel},
  title  = {The development of the auxiliaries},
  year   = {1982},
  booktitle = {Studies in the Romance Verb},
  publisher = {Croom Helm}}
@article{fruyt2011,
  author = {Fruyt, Mich\\`ele},
  title  = {Grammaticalization in Latin},
  journal = {New Perspectives},
  year   = {2011}}
"""

DOC = """\\documentclass[a4paper]{article}
\\usepackage{linguexx}
\\usepackage{natbib}
%s
\\begin{document}
According to \\citet{vincent1982}, and see \\citep[786]{fruyt2011}.

\\ex. An example.
\\end{document}
"""


def _write(tmp_path: Path, decl: str, bib: bool = True) -> Path:
    tex = tmp_path / "paper.tex"
    tex.write_text(DOC % decl, encoding="utf-8")
    if bib:
        (tmp_path / "refs.bib").write_text(BIB, encoding="utf-8")
    return tex


def _rendered(tmp_path: Path, odt: Path) -> str:
    soffice = shutil.which("libreoffice") or shutil.which("soffice")
    if soffice is None:
        pytest.skip("libreoffice not installed")
    subprocess.run([soffice, "--headless", "--convert-to", "pdf",
                    str(odt), "--outdir", str(tmp_path)],
                   check=True, capture_output=True, timeout=300)
    out = subprocess.run(
        ["pdftotext", "-layout", str(odt.with_suffix(".pdf")), "-"],
        check=True, capture_output=True, text=True).stdout
    return " ".join(out.split())


# -- finding the bibliography ---------------------------------------------

@pytest.mark.parametrize("source, expected", [
    (r"\addbibresource{mabiblio.bib}", ["mabiblio.bib"]),
    (r"\bibliography{refs}", ["refs.bib"]),
    (r"\bibliography{a,b}", ["a.bib", "b.bib"]),
    (r"\addbibresource[label=x]{c.bib}", ["c.bib"]),
    ("%" + r"\addbibresource{off.bib}", []),
    ("", []),
])
def test_the_document_is_asked_where_its_bibliography_is(
        source: str, expected: list[str]) -> None:
    r"""Both spellings, the extension added only where bibtex omits it.

    The commented-out case is the one worth having: swapping bibliographies
    by commenting the old line out is the ordinary way to do it, and picking
    up both would be picking up one the author turned off.
    """
    assert scan_bibliography(source) == expected


# -- resolving -------------------------------------------------------------

@pandoc
def test_citations_resolve_against_the_declared_bibliography(
        tmp_path: Path) -> None:
    r"""\citet is author-in-text, \citep is parenthetical, and the locator
    survives.  Those three are what natbib is for."""
    tex = _write(tmp_path, r"\bibliography{refs}")
    odt = tmp_path / "paper.odt"
    assert main([str(tex), "-o", str(odt), "-q"]) == 0

    text = _rendered(tmp_path, odt)
    assert "According to Vincent (1982)" in text, text[:200]
    assert "(Fruyt 2011, 786)" in text, text[:200]


@pandoc
def test_the_reference_list_is_generated(tmp_path: Path) -> None:
    """A paper's citations are not much use without one."""
    tex = _write(tmp_path, r"\bibliography{refs}")
    odt = tmp_path / "paper.odt"
    assert main([str(tex), "-o", str(odt), "-q"]) == 0

    text = _rendered(tmp_path, odt)
    assert "Studies in the Romance Verb" in text, text[-400:]
    assert "Croom Helm" in text, text[-400:]


@pandoc
def test_an_explicit_bibliography_wins_over_the_document(
        tmp_path: Path) -> None:
    """--bibliography is the user answering the question themselves."""
    tex = _write(tmp_path, r"\bibliography{nosuchfile}")
    odt = tmp_path / "paper.odt"
    assert main([str(tex), "-o", str(odt), "-q",
                 "--bibliography", str(tmp_path / "refs.bib")]) == 0
    assert "Vincent (1982)" in _rendered(tmp_path, odt)


# -- degrading -------------------------------------------------------------

@pandoc
def test_an_unresolved_citation_is_visible_rather_than_deleted(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The bug this was all about: the gap in the sentence.

    Asserting the key is THERE, not merely that a warning was printed --
    the old behaviour warned about plenty and still deleted the text.
    """
    tex = _write(tmp_path, r"\bibliography{refs}", bib=False)
    odt = tmp_path / "paper.odt"
    assert main([str(tex), "-o", str(odt)]) == 0

    err = capsys.readouterr().err
    assert "not found" in err, err
    assert "2 citation(s) not resolved" in err, err

    text = _rendered(tmp_path, odt)
    assert "[vincent1982]" in text, text[:200]
    assert "[fruyt2011]" in text, text[:200]
    assert "According to [vincent1982], and see" in text, text[:200]


@pandoc
def test_no_citeproc_still_shows_the_keys(tmp_path: Path) -> None:
    """Opting out of resolution is not opting into losing the text."""
    tex = _write(tmp_path, r"\bibliography{refs}")
    odt = tmp_path / "paper.odt"
    assert main([str(tex), "-o", str(odt), "-q", "--no-citeproc"]) == 0
    assert "[vincent1982]" in _rendered(tmp_path, odt)


@pandoc
def test_several_keys_in_one_citation_all_survive(tmp_path: Path) -> None:
    r"""\citep{a,b} is one Cite with two citations, so the degraded form has
    to print both or it silently halves the reference."""
    tex = tmp_path / "multi.tex"
    tex.write_text(
        "\\documentclass{article}\n\\usepackage{linguexx}\n\\begin{document}\n"
        "See \\citep{vincent1982,fruyt2011}.\n\n\\ex. An example.\n"
        "\\end{document}\n", encoding="utf-8")
    odt = tmp_path / "multi.odt"
    assert main([str(tex), "-o", str(odt), "-q"]) == 0
    assert "[vincent1982, fruyt2011]" in _rendered(tmp_path, odt)


# -- honesty about what is not exact ---------------------------------------

@pandoc
def test_a_flattened_natbib_form_is_named(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    r"""\citeauthor asks for the author WITHOUT the year, and pandoc has one
    author-in-text mode, so it prints the year anyway.  Small, and exactly
    the sort of thing that should not be silent."""
    tex = tmp_path / "forms.tex"
    tex.write_text(
        "\\documentclass{article}\n\\usepackage{linguexx}\n"
        "\\bibliography{refs}\n\\begin{document}\n"
        "\\citeauthor{vincent1982} says so.\n\n\\ex. An example.\n"
        "\\end{document}\n", encoding="utf-8")
    (tmp_path / "refs.bib").write_text(BIB, encoding="utf-8")
    assert main([str(tex), "-o", str(tmp_path / "forms.odt")]) == 0

    err = capsys.readouterr().err
    assert "citeauthor" in err and "suppresses" in err, err


def test_a_commented_out_citation_form_is_not_counted(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    r"""The warning counts occurrences, so it must skip comments like every
    other scan here does."""
    tex = tmp_path / "forms.tex"
    tex.write_text(
        "\\documentclass{article}\n\\usepackage{linguexx}\n"
        "\\bibliography{refs}\n\\begin{document}\n"
        "%\\citeauthor{vincent1982}\n\\citet{vincent1982} says so.\n\n"
        "\\ex. An example.\n\\end{document}\n", encoding="utf-8")
    (tmp_path / "refs.bib").write_text(BIB, encoding="utf-8")
    if shutil.which("pandoc") is None:
        pytest.skip("pandoc not installed")
    assert main([str(tex), "-o", str(tmp_path / "forms.odt")]) == 0
    assert "citeauthor" not in capsys.readouterr().err
