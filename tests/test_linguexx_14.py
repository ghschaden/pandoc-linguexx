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
r"""What linguexx 1.4 changed that reaches the page (plan-linguexx-1.4.md).

Three of its changes reached this converter:

- A reference to an example with a custom label, ``\ex.[(7)]``, prints the
  label -- ``(7)``, a sub-example's ``(5a)``, ``\pref`` ``7`` and ``5a``.
  The converter printed the example's index as a number field, "(1)" and
  "(2a)".  It is text now: a custom label is not a counter, and nothing
  renumbers it.
- Movement arrows, ``\mvto{name}{text}`` and ``\mvfrom{name}{text}``.  The
  converter handed them to pandoc, which deleted the commands with their
  text -- "MVPLAIN stays here end." -- under a warning that said the
  fragment was rendered.  The words stay now; the arrow is not drawn, and
  the run says so.

- Inline verbatim in a dot-syntax example: ``\verb``, fancyvrb's ``\Verb``
  and listings' ``\lstinline``, with stars, options and braces.  The source
  scanner knew only ``\verb``, so a "%" in a ``\Verb`` was a comment and
  linguexx's own tests/verb-dot.tex made pandoc fail; ``\Verb[options]``
  failed in pandoc itself and printed its source; the .docx printed every
  one as source; and each said "unhandled command".

The expected text is not reasoned out: it is what linguexx 1.4 prints for
each document, read off ``TEXINPUTS=<linguexx 1.4>: pdflatex`` and
``pdftotext -layout``.
"""

from __future__ import annotations

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

CUSTOM = r"""\documentclass{article}
\usepackage{linguexx}
\begin{document}
\ex.[(7)]\label{seven} CUSTOMSEVEN.

\ex.[(5)] \a.\label{fivea} SUBA.
\b. SUBB.

\ex. NUMBERED, which refers to \ref{seven} inside an example.

REFS: \ref{seven} and \ref{fivea}; bare \pref{seven} and \pref{fivea}.
\end{document}
"""

#: linguexx 1.4's rendering of CUSTOM.
CUSTOM_LINGUEXX = [
    "NUMBERED, which refers to (7) inside an example.",
    "REFS: (7) and (5a); bare 7 and 5a.",
]

MOVES = r"""\documentclass{article}
\usepackage{linguexx}
\begin{document}
\ex. MVPLAIN \mvto{a}{LANDA} stays here \mvfrom{a}{BASEA} end.

\ex. \gll \mvto[above]{w}{WHAT} did you see \lxMoveFrom{w}{\_\_} \\ what did you see {} \\
\glt `What did you see?'

\end{document}
"""

#: linguexx 1.4's rendering of MOVES, the arrows aside (pdftotext does not
#: give the base position's underscores).
MOVES_LINGUEXX = [
    "MVPLAIN LANDA stays here BASEA end.",
    "WHAT did you see",
]


def _convert(tmp_path: Path, doc: str, target: str, quiet: bool = True) -> tuple[Path, str]:
    tex = tmp_path / "doc.tex"
    tex.write_text(doc, encoding="utf-8")
    out = tmp_path / f"doc.{target}"
    args = [str(tex), "-o", str(out), "--to", target] + (["-q"] if quiet else [])
    assert main(args) == 0
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
def test_a_reference_to_a_custom_label_prints_the_label(tmp_path: Path, target: str) -> None:
    out, _ = _convert(tmp_path, CUSTOM, target)
    text = _text(out)
    for line in CUSTOM_LINGUEXX:
        assert line in text, f"{line!r} not in:\n{text}"


@pandoc
@pytest.mark.parametrize("target", ["odt", "docx"])
def test_a_reference_to_a_custom_label_is_no_field(tmp_path: Path, target: str) -> None:
    r"""The only numbered example is the third, and nothing refers to it:
    every reference in CUSTOM is to a custom label, so none is a field --
    one would point at a number no custom-labelled example has."""
    _, xml = _convert(tmp_path, CUSTOM, target)
    marker = "<text:sequence-ref " if target == "odt" else " REF NumEx"
    assert xml.count(marker) == 0, xml.count(marker)


@pandoc
@soffice
@pytest.mark.parametrize("target", ["odt", "docx"])
def test_the_words_of_a_movement_stay(tmp_path: Path, target: str) -> None:
    out, _ = _convert(tmp_path, MOVES, target)
    text = _text(out)
    for line in MOVES_LINGUEXX:
        assert line in text, f"{line!r} not in:\n{text}"


@pandoc
def test_a_movement_says_its_arrow_is_not_drawn(tmp_path: Path, capsys) -> None:
    _convert(tmp_path, MOVES, "odt", quiet=False)
    err = capsys.readouterr().err
    said = [line for line in err.splitlines() if "movement arrows" in line]
    assert len(said) == 1, f"once per document, got {said}"
    assert "the words they mark are kept" in said[0]
    assert "fragment rendered by pandoc" not in err, err


VERBATIM = r"""\documentclass{article}
\usepackage{linguexx}
\usepackage{fancyvrb}
\usepackage{listings}
\begin{document}
\ex. VDPLAIN \verb|dv_%$#{}~^\| tail.

\ex. VDSTAR \verb*|dv star| tail.

\ex. \a. VDSUB \Verb|dV_%$#{}| tail.
\b. VDVSTAR \Verb*[formatcom={\def\lxtest{]}}]|dV star| tail.
\c. VDLST \lstinline|dl_%$#{}| tail.
\d. VDLSTB \lstinline[basicstyle={\ttfamily}]{dlb_%#{y} z tail.

\ex. \gll VDG \verb|g_1| \Verb|h_1| \lstinline{k_1} end\\
          GA GB GC GD GE\\

\ex. VDNEXT plain.

VDPROSE after the examples.
\end{document}
"""

#: linguexx 1.4's rendering of VERBATIM: the lines of its tests/verb-dot.tex
#: that VERBATIM keeps, pdftotext -layout.
VERBATIM_LINGUEXX = [
    "VDPLAIN dv_%$#{}~^\\ tail.",
    "VDSTAR dv\u2423star tail.",
    "VDSUB dV_%$#{} tail.",
    "VDVSTAR dV\u2423star tail.",
    "VDLST dl_%$#{} tail.",
    "VDLSTB dlb_%#{y z tail.",
    "VDG g_1 h_1 k_1 end",
    "VDNEXT plain.",
    "VDPROSE after the examples.",
]


@pandoc
@soffice
@pytest.mark.parametrize("target", ["odt", "docx"])
def test_inline_verbatim_prints_what_linguexx_prints(tmp_path: Path, target: str) -> None:
    out, _ = _convert(tmp_path, VERBATIM, target)
    text = _text(out)
    for line in VERBATIM_LINGUEXX:
        assert line in text, f"{line!r} not in:\n{text}"


@pandoc
def test_inline_verbatim_is_no_warning(tmp_path: Path, capsys) -> None:
    r"""linguexx 1.4 allows it in an example, and it comes out right: an
    "unhandled command \verb" for each one was noise that hid the rest."""
    _convert(tmp_path, VERBATIM, "odt", quiet=False)
    err = capsys.readouterr().err
    assert "unhandled command" not in err and "fallback failed" not in err, err


def test_a_caret_written_as_a_command_is_a_caret() -> None:
    r"""docx2linguexx writes a "^" as \textasciicircum{}, which the renderer
    did not know: the cell fell back to its source, and the round trip of
    linguexx's tests/verb-dot.tex (a "^" in a \verb) failed on it."""
    from linguexx2odt.inline import InlineRenderer
    assert InlineRenderer().plain(r"a\textasciicircum{}b") == "a^b"
