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
r"""The .docx target: numbers, references, and what it does not do yet.

Phase 2 of plan-docx.md.  What is claimed here is narrow on purpose — a
plain example and a reference to it — and the tests say where the edge is,
because a target that quietly lays a gloss out wrong is worse than one that
says it cannot.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from linguexx2odt.cli import main

HERE = Path(__file__).parent
ROOT = HERE.parent
SCHEMAS = ROOT / ".ooxml-schemas"

pandoc = pytest.mark.skipif(shutil.which("pandoc") is None,
                            reason="pandoc not installed")

PLAIN = r"""\documentclass{article}
\usepackage{linguexx}
\begin{document}
\ex.\label{one} A first example.

\ex.\label{two} A second example.

Prose referring to \ref{one} and \ref{two}, and bare \pref{one}.
\end{document}
"""


def build(tmp_path: Path, source: str, name: str = "t") -> Path:
    src = tmp_path / f"{name}.tex"
    src.write_text(source, encoding="utf-8")
    out = tmp_path / f"{name}.docx"
    assert main([str(src), "--to", "docx", "-o", str(out), "-q"]) == 0
    return out


def document_xml(docx: Path) -> str:
    return zipfile.ZipFile(docx).read("word/document.xml").decode("utf-8")


def cached_values(docx: Path) -> list[str]:
    """What each field shows to a reader that does not recalculate."""
    # the run may carry properties (font, size, small caps) before its text
    return re.findall(
        r'separate"/></w:r><w:r>(?:<w:rPr>.*?</w:rPr>)?<w:t[^>]*>([^<]*)</w:t>',
        document_xml(docx))


@pandoc
def test_numbers_and_references_are_fields(tmp_path: Path) -> None:
    xml = document_xml(build(tmp_path, PLAIN))
    assert xml.count("SEQ NumEx") == 2, "one SEQ field per example"
    assert xml.count("REF NumEx") == 3, r"\ref, \ref and \pref"
    assert 'w:name="NumEx0"' in xml and 'w:name="NumEx1"' in xml


@pandoc
def test_cached_values_are_correct(tmp_path: Path) -> None:
    """Fact 12, and the reason it is a fact.

    A field carries the text shown by a reader that does not recalculate,
    and readers differ: LibreOffice recalculates on open, OnlyOffice 9.4
    does not and showed (1) (1) with both references reading 99.  So the
    cache is not a hint to be corrected later — it is what somebody sees.
    """
    assert cached_values(build(tmp_path, PLAIN)) == ["1", "2", "1", "2", "1"]


@pandoc
def test_the_bookmark_wraps_the_field_and_not_the_line(tmp_path: Path) -> None:
    r"""Fact 3: otherwise \ref gives back the whole example, not its number."""
    xml = document_xml(build(tmp_path, PLAIN))
    m = re.search(r'<w:bookmarkStart[^>]*w:name="NumEx0"/>(.*?)<w:bookmarkEnd',
                  xml, re.S)
    assert m, "no bookmark around the first number"
    inside = m.group(1)
    assert "SEQ NumEx" in inside, "the bookmark does not contain the field"
    assert "A first example" not in inside, (
        "the bookmark swallowed the example text; a reference to it would "
        "give back the line rather than the number")


GLOSS = r"""\documentclass{article}
\usepackage{linguexx}
\begin{document}
\exg. il mio libro\\
the my \lpzg{3sg}\\
\glt `my book'
\end{document}
"""


@pandoc
def test_a_gloss_becomes_a_grid(tmp_path: Path) -> None:
    """Phase 3: tiers in columns, not run together.

    Three object words and three gloss words means three body columns, and
    a cell per word on each tier -- which in OOXML is counted by span, not
    by element, because a gridSpan of 3 is one cell occupying three
    columns and ODF's covered-cell placeholders have no counterpart.
    """
    xml = document_xml(build(tmp_path, GLOSS, "g"))
    words = [t for t in re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml) if t.strip()]
    for w in ("il", "mio", "libro", "the", "my"):
        assert w in words, f"{w!r} missing from {words}"
    assert xml.count("<w:tr>") >= 3, "object tier, gloss tier and translation"


@pandoc
def test_inline_markup_is_interpreted_not_copied(tmp_path: Path) -> None:
    r"""\lpzg{3sg} is small capitals, not eleven literal characters.

    esc() alone put the command in the document verbatim.  It also matters
    for the geometry: the width estimator measured the *drawn* text, small
    caps and all, so a document that draws something else has columns
    sized for a string it does not contain.
    """
    xml = document_xml(build(tmp_path, GLOSS, "m"))
    assert "\\lpzg" not in xml, "the command reached the document literally"
    assert "3sg" in xml
    assert '<w:rStyle w:val="LxLeipzig"/>' in xml, (
        "the Leipzig gloss does not carry the small-caps character style")
    assert "\u2018my book\u2019" in xml, "the quotes were not turned"


@pandoc
@pytest.mark.skipif(not (SCHEMAS / "wml.xsd").is_file(),
                    reason="run `make schemas` to fetch the ECMA-376 schemas")
def test_the_output_is_schema_valid(tmp_path: Path) -> None:
    """Conformance, which is most of what makes Word refuse a file.

    This one is allowed to skip where the rest of the suite is not: it
    needs an 8 MB download rather than an installed tool, and making every
    contributor fetch a standard to run the tests would be a worse trade.
    `make schemas` once, and it runs from then on.
    """
    docx = build(tmp_path, PLAIN)
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "validate_docx.py"),
                        str(docx)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


@pandoc
@pytest.mark.skipif(shutil.which("soffice") is None, reason="soffice not installed")
def test_it_renders_the_same_as_the_odt_target(tmp_path: Path) -> None:
    """Two targets, one document, one reading.

    The strongest check available without opening Word: whatever the
    markup, the page has to say the same thing.
    """
    def render(path: Path) -> str:
        outdir = tmp_path / (path.suffix[1:] + "-pdf")
        outdir.mkdir(exist_ok=True)
        subprocess.run(["soffice", "--headless", "--convert-to", "pdf",
                        str(path), "--outdir", str(outdir)],
                       capture_output=True, timeout=300)
        pdf = outdir / (path.stem + ".pdf")
        text = subprocess.run(["pdftotext", str(pdf), "-"],
                              capture_output=True, text=True).stdout
        # drop the page number a renderer may add
        return " ".join(text.split())

    docx = build(tmp_path, PLAIN, "both")
    odt = tmp_path / "both.odt"
    src = tmp_path / "both.tex"
    assert main([str(src), "-o", str(odt), "-q"]) == 0

    from_docx, from_odt = render(docx), render(odt)
    expected = ("(1) A first example. (2) A second example. "
                "Prose referring to (1) and (2), and bare 1.")
    assert from_docx.startswith(expected), from_docx
    assert from_odt.startswith(expected), from_odt


BANDED = r"""\documentclass{article}
\usepackage{linguexx}
\begin{document}
\exg. Der ausserordentlich lange Hund bellte laut.\\
the extraordinarily long dog barked loudly\\
\glt `The dog barked.'

\ex.
\a. *a judged sub-example
\b. a plain one
\end{document}
"""


@pandoc
@pytest.mark.skipif(shutil.which("soffice") is None, reason="soffice not installed")
def test_a_gloss_sits_under_its_object_word(tmp_path: Path) -> None:
    """The columns are the feature; measure them on the rendered page.

    Every gloss word must start at exactly the x of the object word above
    it. This caught the real Phase 3 defect: the grid was structurally
    right and the words wrapped inside it, because the widths came from
    _ADVANCE (Liberation Serif, 12pt) and pandoc's reference.docx draws in
    neither. A column correct for a font the document does not use is not
    a correct column.
    """
    docx = build(tmp_path, BANDED, "b")
    outdir = tmp_path / "pdf"
    outdir.mkdir()
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf",
                    str(docx), "--outdir", str(outdir)],
                   capture_output=True, timeout=300)
    bbox = subprocess.run(
        ["pdftotext", "-bbox", str(outdir / "b.pdf"), "-"],
        capture_output=True, text=True).stdout
    words = [(float(x), float(y), w) for x, y, w in re.findall(
        r'<word xMin="([\d.]+)" yMin="([\d.]+)"[^>]*>([^<]+)</word>', bbox)]
    assert words, "nothing rendered"

    # Per ROW, not a flat word->x map: "dog" is in the gloss tier and in
    # the translation, and a flat map compares the wrong pair — which is
    # how the first version of this test failed against correct output.
    rows: dict[float, dict[str, float]] = {}
    for x, y, w in words:
        rows.setdefault(round(y / 3) * 3, {})[w] = x
    by_y = [rows[k] for k in sorted(rows)]
    obj = next(r for r in by_y if "Der" in r)
    gloss = next(r for r in by_y if "the" in r and "Der" not in r)

    for object_word, gloss_word in (("Der", "the"), ("lange", "long"),
                                    ("Hund", "dog"), ("bellte", "barked")):
        assert object_word in obj, f"{object_word!r} not on the object tier"
        assert gloss_word in gloss, f"{gloss_word!r} not on the gloss tier"
        assert obj[object_word] == pytest.approx(gloss[gloss_word], abs=1.0), (
            f"{gloss_word!r} at {gloss[gloss_word]:.1f} is not under "
            f"{object_word!r} at {obj[object_word]:.1f}"
        )

    # and nothing wrapped: a wrapped word appears as two fragments
    rendered = {w for _x, _y, w in words}
    assert "ausserordentlich" in rendered, (
        f"a word wrapped inside its column: {sorted(rendered)}")


@pandoc
@pytest.mark.skipif(shutil.which("soffice") is None, reason="soffice not installed")
def test_a_judgment_mark_hangs_against_its_text(tmp_path: Path) -> None:
    r"""The mark sits snug against the example, as linguexx \llap's it.

    Left-aligned in its own column it floats, leaving a hole between the
    mark and the word it judges — measured at 10pt before the judgment
    cell was given a right-aligned paragraph.
    """
    docx = build(tmp_path, BANDED, "j")
    outdir = tmp_path / "jpdf"
    outdir.mkdir()
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf",
                    str(docx), "--outdir", str(outdir)],
                   capture_output=True, timeout=300)
    text = subprocess.run(["pdftotext", str(outdir / "j.pdf"), "-"],
                          capture_output=True, text=True).stdout
    assert "*a judged" in " ".join(text.split()), (
        "the mark is not against its text; it has its own column but not "
        "the right alignment that makes it hang")


PARADIGM = r"""\documentclass{article}
\usepackage{linguexx}
\begin{document}
\ex.
\ag. il mio libro\\
the my book\\
\bg. Ich habe geschlafen heute\\
I have slept today\\
\end{document}
"""


@pandoc
def test_every_row_adds_up_to_the_grid_by_span(tmp_path: Path) -> None:
    """The OOXML invariant, and the one idiom that is not a transcription.

    ODF spans a cell and then emits a `covered-table-cell` placeholder for
    each column swallowed, so every row has one element per grid column and
    counting elements is enough. OOXML spans with `w:gridSpan` and emits
    NOTHING for the columns taken: a row is complete when its spans total
    the grid, and a row that merely has the right number of cells is a
    table Word will render as a mess.

    A paradigm of unequal tiers is used because it is what produces spans
    at all — the grid is the union of both items' column boundaries, so a
    word of one item covers several columns of the other. With equal tiers
    every span is 1 and this test cannot fail.
    """
    xml = document_xml(build(tmp_path, PARADIGM, "p"))
    n_cols = len(re.findall(r"<w:gridCol\b", xml))
    assert n_cols > 1, "no grid to speak of"

    spans_seen = [int(s) for s in re.findall(r'<w:gridSpan w:val="(\d+)"/>', xml)]
    assert any(s > 1 for s in spans_seen), (
        "no column spans in a paradigm of unequal tiers; this test cannot "
        "prove anything about spans unless the input produces some")

    for i, row in enumerate(re.findall(r"<w:tr>(.*?)</w:tr>", xml, re.S)):
        cells = len(re.findall(r"<w:tc>", row))
        spanned = sum(int(s) - 1
                      for s in re.findall(r'<w:gridSpan w:val="(\d+)"/>', row))
        assert cells + spanned == n_cols, (
            f"row {i} covers {cells + spanned} of {n_cols} columns "
            f"({cells} cells, {spanned} spanned)"
        )


TWO_BANDS = r"""\documentclass{article}
\usepackage{linguexx}
\begin{document}
\exg. Dies ist ein extrem langes Beispiel um zu zeigen, was passiert,
      wenn die Grenze einer Linie erst einmal \"uberschritten ist\\
      This is a extreme long example for to show what happens
      when the border a.gen line first once trespassed is\\
\glt `Just a test'
\end{document}
"""


@pandoc
@pytest.mark.parametrize("source", ["TWO_BANDS", "PARADIGM"])
def test_every_cell_is_as_wide_as_the_columns_it_spans(tmp_path: Path,
                                                       source: str) -> None:
    """A cell's w:tcW is the sum of the grid columns it covers.

    LibreOffice and Word lay a fixed table out from w:tblGrid, so a wrong
    tcW goes unseen there -- and OnlyOffice lays it out from the cells
    (plan-addins.md, S8 fact 2).  The width used to be summed from the
    columns at the word's *index*, which is its column only in a table of
    one band and one body: a continuation band starts back at column 0, and
    a paradigm's words land wherever the grid union put them.  OnlyOffice
    drew the banded example below as letters stacked in slivers ("Bei",
    "spi", "el"; "was passiert" as single characters) while LibreOffice drew
    it correctly.
    """
    xml = document_xml(build(tmp_path, globals()[source], "w"))
    grid = [int(g) for g in re.findall(r'<w:gridCol w:w="(\d+)"/>', xml)]
    bad = []
    for i, row in enumerate(re.findall(r"<w:tr>(.*?)</w:tr>", xml, re.S)):
        col = 0
        for width, span in re.findall(
                r'<w:tcW w:w="(\d+)" w:type="dxa"/>(?:<w:gridSpan w:val="(\d+)"/>)?', row):
            span = int(span or 1)
            want = sum(grid[col:col + span])
            # each width is rounded to whole dxa on its own, so a cell over
            # n columns may differ from their sum by up to n
            if abs(int(width) - want) > span:
                bad.append(f"row {i}, columns {col}..{col + span - 1}: "
                           f"tcW {width}, the grid says {want}")
            col += span
    assert not bad, "\n".join(bad[:8]) + (f"\n... {len(bad) - 8} more" if len(bad) > 8 else "")


@pandoc
def test_the_styles_an_example_uses_are_defined(tmp_path: Path) -> None:
    """Phase 4, and fact 6 is why it is not optional.

    A `w:pStyle` naming a style the document does not define is not an
    error: the reference survives and the paragraph renders with the
    default.  So an example can reference LxExampleCell, look almost right,
    and be set in a font the columns were not measured for -- which is
    exactly what happened between removing the per-run font and injecting
    the styles.  Every style referenced must exist.
    """
    docx = build(tmp_path, BANDED, "s")
    xml = document_xml(docx)
    styles = zipfile.ZipFile(docx).read("word/styles.xml").decode("utf-8")

    referenced = set(re.findall(r'<w:pStyle w:val="(Lx[A-Za-z]+)"/>', xml))
    referenced |= set(re.findall(r'<w:rStyle w:val="(Lx[A-Za-z]+)"/>', xml))
    assert referenced, "the example references no styles at all"

    defined = set(re.findall(r'w:styleId="(Lx[A-Za-z]+)"', styles))
    missing = sorted(referenced - defined)
    assert not missing, (
        f"referenced but never defined: {missing} — they will render with "
        f"Word's defaults, in a font the columns were not measured for")


@pandoc
def test_the_body_font_is_declared_once_on_the_style(tmp_path: Path) -> None:
    """Fact 10, settled where it belongs.

    The column widths come from _ADVANCE (Liberation Serif, 12pt).  Phase 3
    named that face on every single run, because nothing declared the
    styles yet and a column measured for one font and drawn in another
    wraps.  It belongs on the style a user can edit, and once there the
    runs should carry no font of their own.
    """
    docx = build(tmp_path, BANDED, "f")
    xml = document_xml(docx)
    styles = zipfile.ZipFile(docx).read("word/styles.xml").decode("utf-8")

    assert "w:rFonts" not in xml, (
        "a run still carries direct font formatting; the document default "
        "should be the only place the face is named")

    # On the DOCUMENT DEFAULT, and not on the example style.  Both keep the
    # columns right; only the first keeps the examples in the same face as
    # the prose around them, which the ODT target gets for free because its
    # LxExampleCell inherits from Standard and names no font.  Put it on the
    # style and a reader sees the examples change typeface mid-page.
    default = re.search(r"<w:rPrDefault>.*?</w:rPrDefault>", styles, re.S)
    assert default, "styles.xml has no document default to carry the face"
    fonts = re.findall(r'<w:rFonts[^>]*w:ascii="([^"]+)"', default.group(0))
    assert fonts, (
        "the document default names no face, so it resolves to a theme font "
        "and the columns are measured for something else")

    cell = re.search(r'<w:style [^>]*w:styleId="LxExampleCell".*?</w:style>',
                     styles, re.S)
    assert cell, "no LxExampleCell style"
    assert "w:ascii=" not in cell.group(0), (
        "the example style names a face of its own, so examples will not "
        "match the prose around them")

    # exactly one rFonts in the default: prepending beside pandoc's theme
    # font left both, and the theme one won
    assert len(re.findall(r"<w:rFonts", default.group(0))) == 1, (
        "more than one rFonts in the document default; the last one wins "
        "and it may not be ours")


@pandoc
def test_the_space_around_an_example_is_a_styled_row(tmp_path: Path) -> None:
    """Spacer rows, as in the ODT target, and the plan asked why.

    w:spacing on the first and last paragraphs was the alternative. Both
    make the gap a style a user can edit; the rows keep the two targets one
    shape, so a document converted either way is the same object and one
    vocabulary explains both — and w:spacing would additionally have to
    answer what an example whose first row is also its last should do.

    Measured between two examples: 24.0pt in the .docx and 24.0pt in the
    .odt, from the same source. (The gap at the very start and end of the
    document differs, because pandoc's reference.docx puts its own spacing
    around a table; that is the reference document's business, not this
    row's.)
    """
    xml = document_xml(build(tmp_path, PLAIN, "sp"))
    for style in ("LxExampleSpaceAbove", "LxExampleSpaceBelow"):
        assert f'<w:pStyle w:val="{style}"/>' in xml, f"no {style} row"

    # the spacer rows top and tail each example, and span the whole grid
    rows = re.findall(r"<w:tr>(.*?)</w:tr>", xml, re.S)
    assert "LxExampleSpaceAbove" in rows[0], "the first row is not the spacer"
    assert "LxExampleSpaceBelow" in rows[-1], "the last row is not the spacer"
