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
r"""Raw LaTeX that reaches the writer is deleted, so the run must say so.

``\Next``, an unresolved ``Cite``, ``\input``: three times the same loss,
each found in a real document and fixed on its own, none of them warned
about.  One net over the finished AST names whatever is left, so the
fourth is reported by the run that meets it.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from linguexx2odt.cli import main
from linguexx2odt.inject import report_dropped_latex

pandoc = pytest.mark.skipif(shutil.which("pandoc") is None,
                            reason="pandoc not installed")


def _raw(kind: str, text: str) -> dict:
    return {"t": kind, "c": ["latex", text]}


def _report(blocks: list) -> list[str]:
    warnings: list[str] = []
    report_dropped_latex({"blocks": blocks}, warnings.append)
    return warnings


def test_content_is_named_and_counted() -> None:
    blocks = [
        _raw("RawBlock", "\\begin{forest}[S [NP] [VP]]\\end{forest}"),
        {"t": "Para", "c": [_raw("RawInline", "\\tableofcontents"),
                            _raw("RawInline", "\\foo{x}")]},
        _raw("RawBlock", "\\begin{forest}[S]\\end{forest}"),
    ]
    warnings = _report(blocks)
    assert len(warnings) == 1, warnings
    assert "\\begin{forest} (2)" in warnings[0], warnings
    assert "\\tableofcontents" in warnings[0], warnings
    assert "\\foo" in warnings[0], warnings


def test_layout_commands_are_not_reported() -> None:
    """Measured on pandoc 3.10 to arrive raw, and carrying no text: a
    warning for every \\noindent would bury the one that matters."""
    blocks = [{"t": "Para", "c": [_raw("RawInline", "\\noindent "),
                                  _raw("RawInline", "\\vspace*{2cm}"),
                                  _raw("RawInline", "\\setlength{\\parindent}{0pt}")]},
              _raw("RawBlock", "\\maketitle")]
    assert _report(blocks) == []


def test_the_leftovers_of_a_rescued_example_are_not_reported() -> None:
    """Freeing an example from multicols leaves its bare \\begin and \\end
    behind; the rescue already names the environment."""
    blocks = [_raw("RawBlock", "\\begin{multicols}{2}\n"),
              _raw("RawBlock", "\n\\end{multicols}")]
    assert _report(blocks) == []


def test_citations_are_left_to_their_own_pass() -> None:
    """A Cite's fallback is raw LaTeX, but citeproc replaces it, or
    _degrade_citations does and says so."""
    cite = {"t": "Cite", "c": [[], [_raw("RawInline", "\\citet{x}")]]}
    assert _report([{"t": "Para", "c": [cite]}]) == []


def test_other_raw_formats_are_not_reported() -> None:
    assert _report([{"t": "RawBlock", "c": ["opendocument", "<x/>"]}]) == []


@pandoc
def test_the_run_names_prose_lost_inside_an_unknown_environment(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tex = tmp_path / "lost.tex"
    tex.write_text(
        "\\documentclass{article}\n\\usepackage{multicol}\n"
        "\\begin{document}\n\\noindent Before.\n\n"
        "\\begin{multicols}{2}\nProse pandoc will not keep.\n\\end{multicols}\n"
        "\\end{document}\n", encoding="utf-8")
    assert main([str(tex), "-o", str(tmp_path / "lost.odt")]) == 0

    err = capsys.readouterr().err
    assert "\\begin{multicols}" in err, err
    assert "noindent" not in err, err


def test_a_layout_command_does_not_hide_what_follows_it() -> None:
    warnings = _report([_raw("RawBlock", "\\centering\n\\vspace{1em}\\Tree [.S a ]")])
    assert len(warnings) == 1 and "\\Tree" in warnings[0], warnings


FALSE_CLAIMS = ("left untouched", "left as LaTeX", "renders it literally",
                "rendered literally", "kept as raw LaTeX", "left as written")


def test_no_warning_claims_the_latex_survives() -> None:
    """Every one of these warnings said the LaTeX was kept -- "left
    untouched", "pandoc renders it literally" -- and in every case, read
    off a converted document, the writer deleted it."""
    from linguexx2odt.extract import parse
    src = r"""\documentclass{article}
\usepackage[langsci]{linguexx}
\begin{document}
\ex. One, \refrange{a}{b} and \begin{itemize}\item x\end{itemize}.

See \refrange{a}{b} and \altn{p}{q}; also \Last and \NNext.
\begin{itemize}\item \ex. Listed.

\end{itemize}
Note.\footnote{\ex. Noted.

}
\ex gb4e form.

\a. Stray.
\end{document}
"""
    warnings = parse(src).warnings
    assert len(warnings) >= 9, warnings
    wrong = [w for w in warnings if any(c in w for c in FALSE_CLAIMS)]
    assert not wrong, "\n".join(wrong)


def test_what_no_table_can_hold_is_named_as_something_to_avoid() -> None:
    r"""\altn, \altg and a list or table inside an example have no form in
    an example table, in either target.  Decided 2026-09-27: not
    approximated, but named, with the advice not to use them in a document
    meant for conversion -- in prose and inside an example alike."""
    from linguexx2odt.extract import parse
    src = r"""\begin{document}
Prose \altn{est}{*sont} and \altg{a}{b}.

\ex. In \altn{est}{*sont} one.

\ex. With \begin{itemize}\item x\end{itemize} and \begin{tabular}{l} y \end{tabular}.

\ex. Plain \refrange{a}{b}.

\end{document}
"""
    warnings = parse(src).warnings
    avoid = [w for w in warnings if "do not use it" in w]
    assert len(avoid) == 5, "\n".join(warnings)
    for name in ("\\altn", "\\altg", "itemize", "tabular"):
        assert any(name in w for w in avoid), (name, avoid)
    assert not any("ranged reference" in w for w in avoid), \
        "a range is representable; it is not something to avoid"
