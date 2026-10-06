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
r"""The way back: docx2linguexx and odt2linguexx (plan-reverse.md, tier A).

The oracle is the forward path.  A document converted to .docx and back
must parse to the examples the original parses to -- every tier, cell,
judgment, translation, annotation, marker and level -- compared as the
converter's own inline renderer reads them, so that ``\"a`` and ``ä`` are
the same text and a renamed label is the same reference.  Nothing else
could say what "the same example" means without inventing it.

What the oracle cannot see is what the forward path never wrote, so the
documents it loses text from are listed in KNOWN_FORWARD_LOSSES with the
reason, rather than taken out of the run.
"""

from __future__ import annotations

import os
import re
import shutil
import zipfile
from pathlib import Path

import pytest

from linguexx2odt import reverse
from linguexx2odt.cli import main as forward
from linguexx2odt.extract import parse
from linguexx2odt.includes import expand_includes
from linguexx2odt.inline import InlineRenderer

HERE = Path(__file__).parent
CASES = sorted((HERE / "cases").glob("*.tex"))
CORPUS_DIR = Path(__file__).resolve().parents[2] / "linguexx" / "tests"
# The underscore files are preambles \input by the others, not documents.
CORPUS = sorted(p for p in CORPUS_DIR.glob("*.tex") if not p.name.startswith("_"))

#: Every corpus document in CI, every fourth in a local run.  A round trip
#: is about a second -- three pandoc runs -- and the 110 documents took a
#: local `make test` from 75 s to three and a half minutes, where CI does
#: them in under a minute.  The sample is fixed, so a local failure is
#: reproducible; LINGUEXX_FULL_CORPUS=1 runs them all.  GitHub Actions sets
#: CI=true, and test_ci_round_trips_the_whole_corpus holds CI to it.
FULL_CORPUS = (os.environ.get("CI") == "true"
               or os.environ.get("LINGUEXX_FULL_CORPUS") == "1")
CORPUS_ROUND_TRIPS = CORPUS if FULL_CORPUS else CORPUS[::4]

pandoc = pytest.mark.skipif(shutil.which("pandoc") is None,
                            reason="pandoc not installed")
soffice = pytest.mark.skipif(shutil.which("soffice") is None,
                             reason="soffice not installed")

#: (document, example index) -> why the way back cannot give it back.
#: Each is the forward path dropping text before the .docx was written;
#: the reader returns what the file holds.
KNOWN_FORWARD_LOSSES: dict[tuple[str, int], str] = {}


# -- the oracle ----------------------------------------------------------

#: Quotes are folded: where the forward path could not render a fragment
#: it printed the source, `x' and all, and that comes back as the
#: characters it shows.  Everything else is compared exactly.
_FOLD = str.maketrans({"`": "'", "‘": "'", "’": "'"})


def _runs(r: InlineRenderer, latex: str) -> list[tuple[str, bool]]:
    out: list[tuple[str, bool]] = []
    for text, sc in r.runs(latex):
        if out and out[-1][1] == sc:
            out[-1] = (out[-1][0] + text, sc)
        else:
            out.append((text, sc))
    return [(" ".join(t.split()).translate(_FOLD), sc)
            for t, sc in out if t.strip()]


def _body(r: InlineRenderer, b) -> dict:
    tiers = []
    for t in b.tiers:
        cells = [_runs(r, c) for c in t.cells]
        while cells and not cells[-1]:
            cells.pop()
        tiers.append(cells)
    # \exsource is set after the translation, in its row: it comes back as
    # part of it (README).
    trailer = " ".join(x for x in (b.translation, b.source) if x)
    return {"judgment": _runs(r, b.judgment), "text": _runs(r, b.text),
            "tiers": tiers, "translation": _runs(r, trailer),
            "annot": _runs(r, b.annot)}


def view(source: str) -> list[dict]:
    res = parse(source)
    r = InlineRenderer()
    r.labels, r.brackets, r.macros = res.labels, res.brackets, res.macros
    return [{"custom": _runs(r, e.custom_label), "head": _runs(r, e.head),
             "body": _body(r, e.body) if e.body is not None else None,
             "items": [(i.level, i.ordinal, i.marker, _body(r, i.body))
                       for i in e.items]}
            for e in res.examples]


def round_trip(tex: Path, tmp_path: Path, kind: str = "docx") -> tuple[str, list[str]]:
    out = tmp_path / f"forward.{kind}"
    assert forward([str(tex), "--to", kind, "-o", str(out), "-q"]) in (0, 1)
    docx = reverse.odt_to_docx(out, tmp_path) if kind == "odt" else out
    back = tmp_path / "back.tex"
    warnings: list[str] = []
    reverse.convert(docx, back, warnings.append)
    return back.read_text(encoding="utf-8"), warnings


def check(tex: Path, tmp_path: Path, kind: str) -> None:
    original = expand_includes(tex.read_text(encoding="utf-8"), tex.parent,
                               lambda _w: None, main=tex).text
    back, warnings = round_trip(tex, tmp_path, kind)
    assert not any("did not survive" in w for w in warnings), warnings
    assert "LXEXAMPLE" not in back and "LXREF" not in back
    a, b = view(original), view(back)
    assert len(a) == len(b), f"{len(a)} examples went in, {len(b)} came back"
    for k, (x, y) in enumerate(zip(a, b)):
        if (tex.name, k) in KNOWN_FORWARD_LOSSES:
            continue
        assert x == y, f"example {k + 1}"


@pandoc
@pytest.mark.parametrize("tex", CASES + CORPUS_ROUND_TRIPS, ids=lambda p: p.stem)
def test_round_trip_through_docx(tex: Path, tmp_path: Path) -> None:
    check(tex, tmp_path, "docx")


#: Through .odt LibreOffice converts each file, a few seconds apiece, so the
#: cases that exercise what its export could change: fields, references,
#: brackets, levels, judgments, annotations, bands.
ODT_CASES = [HERE / "cases" / f"{n}.tex" for n in
             ("labels", "brackets", "sub", "gloss", "judgments", "exannot")]


@pandoc
@soffice
@pytest.mark.parametrize("tex", ODT_CASES, ids=lambda p: p.stem)
def test_round_trip_through_odt(tex: Path, tmp_path: Path) -> None:
    check(tex, tmp_path, "odt")


def test_ci_round_trips_the_whole_corpus() -> None:
    """The local sample is a convenience; CI is where every document runs."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        assert FULL_CORPUS and CORPUS_ROUND_TRIPS == CORPUS
    assert CORPUS_ROUND_TRIPS == CORPUS or len(CORPUS_ROUND_TRIPS) == len(CORPUS[::4])


@pandoc
def test_known_losses_are_still_losses(tmp_path: Path) -> None:
    """KNOWN_FORWARD_LOSSES may not outlive the loss: once the forward
    path keeps the text, the exception must go."""
    for name, k in KNOWN_FORWARD_LOSSES:
        tex = HERE / "cases" / name
        back, _ = round_trip(tex, tmp_path)
        assert view(tex.read_text(encoding="utf-8"))[k] != view(back)[k], (
            f"{name} example {k + 1} now round-trips; remove it from "
            f"KNOWN_FORWARD_LOSSES")


# -- what the LaTeX says -------------------------------------------------

REFS = r"""\documentclass{article}
\usepackage[lazy]{linguexx}
\begin{document}
\ex.\label{one} A first example.

\ex. Unreferenced.

\ex.\label{para}
\a.\label{pa} Premier.
\b. Deuxi\`eme.

See \ref{one}, bare \pref{one}, and \ref{pa}.
\end{document}
"""


def convert(tmp_path: Path, source: str) -> tuple[str, list[str]]:
    tex = tmp_path / "t.tex"
    tex.write_text(source, encoding="utf-8")
    return round_trip(tex, tmp_path)


@pandoc
def test_references_are_references(tmp_path: Path) -> None:
    """A number that is text renumbers nothing, on the way back as on the
    way in.  Labels are made up -- the .docx never had the author's -- and
    only an example something refers to gets one."""
    back, _ = convert(tmp_path, REFS)
    assert r"\ex.\label{ex:1} A first example." in back
    assert r"\ex. Unreferenced." in back
    assert r"\a.\label{ex:3a} Premier." in back
    assert r"See \ref{ex:1}, bare \pref{ex:1}, and \ref{ex:3a}." in back


@pandoc
def test_redefined_brackets_come_back(tmp_path: Path) -> None:
    back, _ = convert(tmp_path, (HERE / "cases" / "brackets.tex").read_text())
    for line in (r"\renewcommand{\ExLBr}{[}", r"\renewcommand{\ExRBr}{]}",
                 r"\renewcommand{\SubExRBr}{)}"):
        assert line in back
    assert r"\renewcommand{\SubExLBr}" not in back
    # [1] reached pandoc's LaTeX as {[}...{]}, and is a \ref all the same
    assert r"Refs: \ref{ex:1}, \pref{ex:1}, \ref{ex:1b}." in back


@pandoc
def test_a_first_level_counted_in_roman_comes_back(tmp_path: Path) -> None:
    r"""\let\Exalph\roman: the sub-examples are i., ii. in the document, and
    a LaTeX that lettered them would number them otherwise.  Every paradigm
    starting at "i." says the document counted that way."""
    back, warnings = convert(tmp_path, r"""\documentclass{article}
\usepackage[lazy]{linguexx}
\let\Exalph\roman
\begin{document}
\ex.\label{top}
\a.\label{one} First.
\b. Second.
\a. Deeper.
\z.
\c. Third.

See \ref{one}.
\end{document}
""")
    assert r"\let\Exalph\roman" in back
    assert not any("does not follow" in w for w in warnings), warnings
    res = parse(back)
    assert [(i.level, i.marker) for i in res.examples[0].items] == [
        (1, "i."), (1, "ii."), (2, "i."), (1, "iii.")]
    assert r"See \ref{ex:1i}." in back


@pandoc
def test_the_gap_between_examples_does_not_come_back(tmp_path: Path) -> None:
    """LxExampleGap exists because Word joins tables that touch; LaTeX
    needs no such paragraph, and pandoc would write an empty one."""
    back, _ = convert(tmp_path, REFS)
    body = back.split(r"\begin{document}")[1]
    assert re.search(r"A first example\.\n\n\\ex\. Unreferenced\.", body)


# -- what Word does to a file --------------------------------------------
#
# The converter writes one shape of each thing; a document saved by Word,
# or edited in it, may hold another.  Each test below takes a converted
# file and rewrites it the way Word would.

def _edit(docx: Path, fn) -> None:
    with zipfile.ZipFile(docx) as z:
        members = {n: z.read(n) for n in z.namelist()}
    doc = members["word/document.xml"].decode("utf-8")
    new = fn(doc)
    assert new != doc, "the edit changed nothing"
    members["word/document.xml"] = new.encode("utf-8")
    with zipfile.ZipFile(docx, "w", zipfile.ZIP_DEFLATED) as z:
        for n, data in members.items():
            z.writestr(n, data)


def _docx(tmp_path: Path, source: str) -> Path:
    tex = tmp_path / "t.tex"
    tex.write_text(source, encoding="utf-8")
    out = tmp_path / "t.docx"
    assert forward([str(tex), "--to", "docx", "-o", str(out), "-q"]) == 0
    return out


def _back(tmp_path: Path, docx: Path) -> tuple[str, list[str]]:
    out = tmp_path / "back.tex"
    warnings: list[str] = []
    reverse.convert(docx, out, warnings.append)
    return out.read_text(encoding="utf-8"), warnings


@pandoc
def test_a_simple_field_and_a_word_bookmark(tmp_path: Path) -> None:
    """Word writes a field as w:fldSimple as readily as as w:fldChar runs,
    and names the bookmarks its own cross-reference dialog makes _Ref..."""
    docx = _docx(tmp_path, REFS)

    def word(doc: str) -> str:
        doc = doc.replace('w:name="NumEx0"', 'w:name="_Ref1234567"')
        return re.sub(
            r'<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            r'<w:r><w:instrText xml:space="preserve"> REF NumEx0 \\h </w:instrText></w:r>'
            r'<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            r'(<w:r>.*?</w:r>)'
            r'<w:r><w:fldChar w:fldCharType="end"/></w:r>',
            r'<w:fldSimple w:instr=" REF _Ref1234567 \\h ">\1</w:fldSimple>',
            doc)
    _edit(docx, word)
    back, _ = _back(tmp_path, docx)
    assert r"See \ref{ex:1}, bare \pref{ex:1}" in back


@pandoc
def test_tracked_changes_are_read_accepted(tmp_path: Path) -> None:
    """pandoc accepts tracked changes in the prose by default, and the
    examples are read the same way: an insertion is text, a deletion not."""
    docx = _docx(tmp_path, r"""\begin{document}
\ex. \gll Dies ist ein Beispiel\\
 this is an example\\

\end{document}""")

    def word(doc: str) -> str:
        doc = doc.replace(
            '<w:r><w:t xml:space="preserve">ein</w:t></w:r>',
            '<w:del w:id="91" w:author="a"><w:r><w:delText>ein</w:delText></w:r></w:del>'
            '<w:ins w:id="92" w:author="a"><w:r><w:t>kein</w:t></w:r></w:ins>', 1)
        return doc
    _edit(docx, word)
    back, _ = _back(tmp_path, docx)
    assert r"\gll Dies ist kein Beispiel\\" in back


@pandoc
def test_direct_formatting_in_a_cell(tmp_path: Path) -> None:
    """The .docx target writes only small capitals into a cell, as a
    character style; a Word user makes a word italic by hand."""
    docx = _docx(tmp_path, r"""\begin{document}
\ex. \gll Dies ist ein Beispiel\\
 this is an \lpzg{indf} example\\

\end{document}""")
    _edit(docx, lambda doc: doc.replace(
        '<w:r><w:t xml:space="preserve">Beispiel</w:t></w:r>',
        '<w:r><w:rPr><w:i/></w:rPr><w:t xml:space="preserve">Beispiel</w:t></w:r>', 1))
    back, _ = _back(tmp_path, docx)
    assert r"\gll Dies ist ein \textit{Beispiel}\\" in back
    assert r"this is an \lpzg{indf} example\\" in back


#: A gloss line as a document made in Writer or Word holds it: the small
#: capitals the linguist typed, as direct formatting, and no LxLeipzig.
NATIVE = r"""\begin{document}
\ex. \gll Der Hund schlief \\
 the dog sleep-\lpzg{pst}.3\lpzg{sg} \\

\end{document}"""


def _native(doc: str) -> str:
    return doc.replace('<w:rPr><w:rStyle w:val="LxLeipzig"/></w:rPr>',
                       '<w:rPr><w:smallCaps/></w:rPr>')


@pandoc
def test_small_capitals_in_an_example_are_leipzig_labels(tmp_path: Path) -> None:
    """Typed small capitals in an example are gloss labels, and linguexx
    sets a gloss label with \\lpzg -- not \\textsc, which a document made
    without LaTeX would otherwise come back with throughout."""
    docx = _docx(tmp_path, NATIVE)
    _edit(docx, _native)
    back, _ = _back(tmp_path, docx)
    assert r"the dog sleep-\lpzg{pst}.3\lpzg{sg}\\" in back
    assert r"\textsc" not in back.split(r"\begin{document}")[1]


@pandoc
def test_punctuation_selected_with_a_label_stays_outside(tmp_path: Path) -> None:
    """The "-" of "-pst" or the "." of "acc." is easily selected with the
    label.  \\lpzg reads a "." inside as a separator between labels, and
    neither is part of one."""
    docx = _docx(tmp_path, NATIVE)

    def word(doc: str) -> str:
        doc = _native(doc)
        return doc.replace(
            '<w:t xml:space="preserve">sleep-</w:t></w:r>'
            '<w:r><w:rPr><w:smallCaps/></w:rPr><w:t xml:space="preserve">pst</w:t></w:r>'
            '<w:r><w:t xml:space="preserve">.3</w:t></w:r>',
            '<w:t xml:space="preserve">sleep</w:t></w:r>'
            '<w:r><w:rPr><w:smallCaps/></w:rPr><w:t xml:space="preserve">-pst.</w:t></w:r>'
            '<w:r><w:t xml:space="preserve">3</w:t></w:r>', 1)
    _edit(docx, word)
    back, _ = _back(tmp_path, docx)
    assert r"the dog sleep-\lpzg{pst}.3\lpzg{sg}\\" in back


@pandoc
def test_a_small_capitals_style_of_the_author_s_own(tmp_path: Path) -> None:
    """A character style that sets small capitals is read for what it
    does, not for what it is called."""
    docx = _docx(tmp_path, NATIVE)
    with zipfile.ZipFile(docx) as z:
        members = {n: z.read(n) for n in z.namelist()}
    styles = members["word/styles.xml"].decode("utf-8").replace(
        "</w:styles>",
        '<w:style w:type="character" w:styleId="Glosse"><w:name w:val="Glosse"/>'
        "<w:rPr><w:smallCaps/></w:rPr></w:style></w:styles>")
    members["word/styles.xml"] = styles.encode("utf-8")
    members["word/document.xml"] = members["word/document.xml"].replace(
        b'<w:rStyle w:val="LxLeipzig"/>', b'<w:rStyle w:val="Glosse"/>')
    with zipfile.ZipFile(docx, "w", zipfile.ZIP_DEFLATED) as z:
        for n, data in members.items():
            z.writestr(n, data)
    back, _ = _back(tmp_path, docx)
    assert r"the dog sleep-\lpzg{pst}.3\lpzg{sg}\\" in back


def _tree_docx(tmp_path: Path, descr: str) -> Path:
    """A converted example whose cell holds an add-in's drawn tree: a drawing
    titled LinguExx tree, its alt text the lines it was typed as."""
    docx = _docx(tmp_path, r"""\begin{document}
\ex. TREEHERE

\end{document}""")
    drawing = (
        '<w:r><w:drawing><wp:inline xmlns:wp="http://schemas.openxmlformats.org/'
        'drawingml/2006/wordprocessingDrawing"><wp:docPr id="7" name="t" '
        f'title="LinguExx tree" descr="{descr}"/></wp:inline></w:drawing></w:r>')
    _edit(docx, lambda doc: doc.replace(
        '<w:r><w:t xml:space="preserve">TREEHERE</w:t></w:r>', drawing))
    return docx


@pandoc
def test_a_drawn_tree_comes_back_as_forest(tmp_path: Path) -> None:
    """The macro's notation is nearly forest's.  Where it is not: a bare word
    among the children is a leaf of its own, which forest would read as part
    of the label; a movement line is a \\draw between named nodes; and the
    root carries baseline, so the number stands level with it."""
    docx = _tree_docx(tmp_path, "[CP [DP,name=wh what] [C&apos; [C did] [VP [V see] "
                                "[DP,name=t __] [{the big tree, roof}]]]]&#10;move t -&gt; wh")
    back, warnings = _back(tmp_path, docx)
    assert ("[CP,baseline [DP,name=wh [what]] [C' [C [did]] [VP [V [see]] "
            "[DP,name=t [\\_\\_]] [{the big tree},roof]]]]") in back
    assert "\\draw[->] (t) to[out=south west, in=south] (wh);" in back
    assert "\\usepackage{forest}" in back and "\\useforestlibrary{linguistics}" in back
    assert not warnings, warnings


@pandoc
def test_a_tree_that_does_not_parse_is_kept_and_said(tmp_path: Path) -> None:
    """Not guessed at: a movement from a node no one named would stop LaTeX,
    and the macro refuses it too."""
    docx = _tree_docx(tmp_path, "[S [NP Kim] [VP sleeps]]&#10;move a -&gt; b")
    back, warnings = _back(tmp_path, docx)
    assert "% [S [NP Kim] [VP sleeps]]\n% move a -> b\n" in back
    assert any("does not parse" in w for w in warnings)
    assert "forest" not in back.split("\\begin{document}")[0]


# -- the commands --------------------------------------------------------

def test_the_commands_are_installed() -> None:
    text = (HERE.parent / "pyproject.toml").read_text(encoding="utf-8")
    assert 'docx2linguexx = "linguexx2odt.reverse:main_docx"' in text
    assert 'odt2linguexx = "linguexx2odt.reverse:main_odt"' in text


def test_each_command_takes_its_own_format(tmp_path: Path) -> None:
    f = tmp_path / "paper.odt"
    f.write_bytes(b"")
    with pytest.raises(SystemExit, match="use odt2linguexx"):
        reverse.main_docx([str(f)])
