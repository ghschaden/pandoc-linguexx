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
r"""References and captions in the document's language (names.py).

Every name was English: a German document's "Abschnitt 1" came out
"section 1", its "Tabelle 1:" caption "Table 1:".  The expected text is
what LaTeX prints for each document, read off ``pdflatex`` and
``pdftotext``; the table itself is checked by tools/measure_names.py.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from linguexx2odt.cli import main
from linguexx2odt.names import detect

pandoc = pytest.mark.skipif(shutil.which("pandoc") is None,
                            reason="pandoc not installed")
soffice = pytest.mark.skipif(shutil.which("soffice") is None
                             or shutil.which("pdftotext") is None,
                             reason="libreoffice or pdftotext not installed")


def _names(preamble: str):
    return detect(preamble + r"\begin{document}")


def test_cleveref_does_not_follow_babel_alone() -> None:
    """Measured: babel's option localises the captions and \\autoref, and
    leaves cleveref English; a class option or cleveref's own reaches it."""
    babel = _names(r"\documentclass{article}\usepackage[ngerman]{babel}\usepackage{cleveref}")
    assert (babel.cref("section"), babel.caption("table")[0], babel.autoref("table")) \
        == ("section", "Tabelle", "Tabelle")
    told = _names(r"\documentclass{article}\usepackage[ngerman]{babel}"
                  r"\usepackage[ngerman]{cleveref}")
    assert told.cref("section") == "Abschnitt"
    by_class = _names(r"\documentclass[11pt,french]{article}\usepackage{babel}"
                      r"\usepackage{cleveref}")
    assert (by_class.cref("table"), by_class.caption("table")) == ("tableau", ("Table", " – "))


def test_babels_main_language_is_the_last_or_main() -> None:
    assert _names(r"\documentclass{article}\usepackage[spanish,french]{babel}"
                  ).caption("table")[0] == "Table"
    assert _names(r"\documentclass{article}\usepackage[french,main=spanish]{babel}"
                  ).caption("table")[0] == "Cuadro"


def test_polyglossia_has_its_own_captions_and_leaves_autoref_english() -> None:
    poly = _names(r"\documentclass{article}\usepackage{polyglossia}"
                  r"\setmainlanguage{french}\usepackage{hyperref}")
    assert poly.caption("table") == ("Tab.", " : ")
    assert poly.autoref("table") == "Table"


def test_a_language_without_names_prints_english_and_says_so() -> None:
    said: list[str] = []
    names = detect(r"\documentclass{article}\usepackage[polish]{babel}\begin{document}",
                   said.append)
    assert names.caption("table")[0] == "Table" and len(said) == 1 and "polish" in said[0]


SOURCE = r"""\documentclass[{lang}]{{article}}
\usepackage[T1]{{fontenc}}
\usepackage{{babel}}
\usepackage{{amsmath}}
\usepackage{{linguexx}}
\usepackage{{hyperref}}
\usepackage{{cleveref}}
\begin{{document}}
\section{{Intro}}\label{{s1}}
\section{{Deux}}\label{{s2}}
\section{{Trois}}\label{{s3}}
\begin{{table}}[h]\caption{{Une table.}}\label{{t1}}
\begin{{tabular}}{{l}} x \\ \end{{tabular}}\end{{table}}
\begin{{figure}}[h]\rule{{1cm}}{{1cm}}\caption{{Une figure.}}\label{{f1}}\end{{figure}}
\begin{{equation}}\label{{e1}} a = b \end{{equation}}
Note.\footnote{{N.\label{{n1}}}}
\begin{{enumerate}}\item un\label{{i1}}\item deux\label{{i2}}\end{{enumerate}}

REFS: A \cref{{s1}} B \Cref{{t1}} C \cref{{f1}} D \cref{{e1}} E \cref{{n1}} F \cref{{i1,i2}}
G \cref{{s1,s2,s3}} H \cref{{s1,t1,e1}} I \autoref{{t1}} J \autoref{{f1}} K \cpageref{{s2}}
L \Cref{{f1}}.
\end{{document}}
"""

#: LaTeX's rendering of SOURCE in each language: the caption and the
#: references.  (French babel also sets "REFS :" with a space before the
#: colon, which is prose typography and not this.)
LATEX = {
    "french": ["Table 1 – Une table.",
               "A section 1 B Tableau 1 C figure 1 D équation (1) E note 1 F points 1 et 2 "
               "G sections 1 à 3 H section 1, tableau 1, et équation (1) I tableau 1 "
               "J figure 1 K page 1 L Figure 1."],
    "ngerman": ["Tabelle 1: Une table.",
                "A Abschnitt 1 B Tabelle 1 C Abb. 1 D Gleichung (1) E Fußnote 1 "
                "F Punkte 1 und 2 G Abschnitte 1 bis 3 H Abschnitt 1, Tabelle 1 und "
                "Gleichung (1) I Tabelle 1 J Abbildung 1 K Seite 1 L Abbildung 1."],
}


@pandoc
@soffice
@pytest.mark.parametrize("target", ["odt", "docx"])
@pytest.mark.parametrize("lang", sorted(LATEX))
def test_references_print_what_latex_prints_in_the_documents_language(
        tmp_path: Path, lang: str, target: str) -> None:
    tex = tmp_path / "doc.tex"
    tex.write_text(SOURCE.format(lang=lang), encoding="utf-8")
    out = tmp_path / f"doc.{target}"
    assert main([str(tex), "-o", str(out), "--to", target, "-q"]) == 0
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf",
                    "--outdir", str(tmp_path), str(out)],
                   check=True, capture_output=True, timeout=120)
    text = " ".join(subprocess.run(["pdftotext", str(out.with_suffix(".pdf")), "-"],
                                   check=True, capture_output=True, text=True).stdout.split())
    for line in LATEX[lang]:
        assert line in text, f"{line!r} not in:\n{text}"
