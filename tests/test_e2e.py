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

"""End-to-end: demo.tex -> .odt, then assert on the real artefact.

The headless-render assertions are the ones that matter — they are the
only check that LibreOffice *evaluates* the fields rather than merely
tolerating them.  They skip cleanly where soffice is absent (CI without
LibreOffice), but the XML-level assertions always run.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from linguexx2odt import postprocess
from linguexx2odt.cli import main

HERE = Path(__file__).parent
DEMO = HERE / "e2e" / "demo.tex"
CM = 72 / 2.54

pandoc = pytest.mark.skipif(shutil.which("pandoc") is None, reason="pandoc not installed")
soffice = pytest.mark.skipif(shutil.which("soffice") is None, reason="soffice not installed")


@pytest.fixture(scope="module")
def converted(tmp_path_factory) -> Path:
    if shutil.which("pandoc") is None:
        pytest.skip("pandoc not installed")
    out = tmp_path_factory.mktemp("e2e") / "demo.odt"
    assert main([str(DEMO), "-o", str(out), "-q"]) == 0
    return out


@pytest.fixture(scope="module")
def pdf(converted: Path) -> Path:
    if shutil.which("soffice") is None:
        pytest.skip("soffice not installed")
    outdir = converted.parent
    subprocess.run(
        ["soffice", "--headless", f"-env:UserInstallation=file://{outdir}/.lo",
         "--convert-to", "pdf", "--outdir", str(outdir), str(converted)],
        check=True, capture_output=True, timeout=240,
    )
    result = outdir / "demo.pdf"
    assert result.exists()
    return result


# -- the ODT itself --------------------------------------------------------

@pandoc
def test_zip_layout(converted: Path) -> None:
    """mimetype must be the first entry and STORED, or nothing opens it."""
    with zipfile.ZipFile(converted) as z:
        infos = z.infolist()
    assert infos[0].filename == "mimetype"
    assert infos[0].compress_type == zipfile.ZIP_STORED


@pandoc
@pytest.mark.parametrize("member", ["content.xml", "styles.xml", "meta.xml"])
def test_xml_is_well_formed(converted: Path, member: str) -> None:
    ET.fromstring(postprocess.read(converted, member))


@pandoc
def test_one_sequence_field_per_example(converted: Path) -> None:
    content = postprocess.read(converted, "content.xml")
    fields = re.findall(r'<text:sequence [^>]*text:name="NumEx"', content)
    assert len(fields) == 12, "demo.tex has 12 convertible examples"
    assert content.count('text:name="NumEx"') == len(fields) + 1  # + the declaration


@pandoc
def test_sequence_is_declared(converted: Path) -> None:
    content = postprocess.read(converted, "content.xml")
    decls = re.search(r"<text:sequence-decls>.*?</text:sequence-decls>", content, re.S)
    assert decls and 'text:name="NumEx"' in decls.group(0)


@pandoc
def test_cross_references_became_fields(converted: Path) -> None:
    content = postprocess.read(converted, "content.xml")
    refs = re.findall(r'<text:sequence-ref[^>]*text:ref-name="(refNumEx\d+)"', content)
    assert len(refs) == 3, "demo.tex makes three \\ref calls"
    assert "[ex:first]" not in content, "a \\ref was left as pandoc's literal fallback"


@pandoc
def test_every_referenced_style_is_defined(converted: Path) -> None:
    """A raw block referencing an undefined style renders unformatted, and
    nothing warns — so check the two files agree."""
    content = postprocess.read(converted, "content.xml")
    styles = postprocess.read(converted, "styles.xml")
    defined = set(re.findall(r'style:name="([^"]+)"', content + styles))
    used = set(re.findall(r'(?:text|table):style-name="(Lx[^"]+)"', content))
    assert used <= defined, f"undefined styles referenced: {sorted(used - defined)}"


@pandoc
def test_tables_fit_the_text_block(converted: Path) -> None:
    content = postprocess.read(converted, "content.xml")
    for m in re.finditer(r'style:name="LxExTable\d+".*?style:width="([\d.]+)cm"', content):
        assert float(m.group(1)) <= 17.001


# -- what LibreOffice actually renders -------------------------------------

def _words(pdf: Path):
    """(text, x, y) for every word in the document, in reading order.

    y is offset per page so that sorting by y keeps pages in order — the
    demo spills onto a second page and assertions must not stop at the
    first one."""
    xml = subprocess.run(["pdftotext", "-bbox", str(pdf), "-"],
                         check=True, capture_output=True, text=True).stdout
    ns = {"x": "http://www.w3.org/1999/xhtml"}
    out = []
    for n, page in enumerate(ET.fromstring(xml).findall(".//x:page", ns)):
        offset = n * (float(page.get("height")) + 1)
        out += [(w.text, float(w.get("xMin")), float(w.get("yMin")) + offset)
                for w in page.findall(".//x:word", ns)]
    return out


@soffice
def test_numbers_are_evaluated_not_echoed(pdf: Path) -> None:
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                          check=True, capture_output=True, text=True).stdout
    for n in range(1, 13):
        assert f"({n})" in text, f"example number ({n}) never rendered"


@soffice
def test_cross_references_resolve(pdf: Path) -> None:
    text = " ".join(
        subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                       check=True, capture_output=True, text=True).stdout.split()
    )
    assert "refer back to (1) and forward to (12)" in text
    assert "reference to a sub-example: (9a)" in text


def _occurrence(words, token: str, nth: int = 0) -> float:
    """x of the nth occurrence of *token*, in reading order."""
    hits = [x for t, x, _y in sorted(words, key=lambda w: (w[2], w[1])) if t == token]
    assert len(hits) > nth, f"{token!r} occurs {len(hits)} times, wanted #{nth}"
    return hits[nth]


def _after(words, leading: str) -> list[float]:
    """x of the token following *leading*, once per line it starts.

    Measuring the *next* token, not the leading one, is how
    ../linguexx/tests/judgment-align.tex does it — and it is the only
    reading that survives a right-aligned judgment mark, because a mark
    snug against the text is merged into the leading token by pdftotext
    ("*This"), which perturbs that token's xMin but nothing after it.
    """
    rows: dict[float, list[tuple[float, str]]] = {}
    for text, x, y in words:
        rows.setdefault(round(y), []).append((x, text))
    out = []
    for y in sorted(rows):
        line = sorted(rows[y])
        for i, (_x, text) in enumerate(line[:-1]):
            if text == leading or text.endswith(leading):
                out.append(line[i + 1][0])
                break
    return out


@soffice
def test_judgment_marks_do_not_shift_the_text(pdf: Path) -> None:
    """R-JUDG, the invariant ../linguexx/tests/judgment-align.tex pins:
    the text block starts at the same x whether or not a judgment mark
    precedes it — both within one example and across examples."""
    words = _words(pdf)

    # (1) "This is a first example."  vs  (2) "*This one is ungrammatical."
    main = _after(words, "This")
    assert len(main) >= 2, "expected both main examples to lead with 'This'"
    assert abs(main[0] - main[1]) < 1.0, (
        f"a judgment mark shifted the text block across examples: {main[:2]}"
    )

    # (3) a. "*Sentences like …"  vs  b. "Sentences like …"
    sub = _after(words, "Sentences")
    assert len(sub) == 2, "expected both sub-examples to lead with 'Sentences'"
    assert abs(sub[0] - sub[1]) < 1.0, (
        f"a judgment mark shifted a sub-example's text: {sub}"
    )


@soffice
def test_gloss_columns_align(pdf: Path) -> None:
    """Object-language words sit directly above their glosses."""
    words = _words(pdf)
    anchor = next(y for t, _x, y in words if t == "Esto")
    baselines = sorted({y for _t, _x, y in words if y > anchor + 3})
    obj = {t: x for t, x, y in words if abs(y - anchor) < 3}
    gloss = {t: x for t, x, y in words if abs(y - baselines[0]) < 3}
    for o, g in (("Esto", "this"), ("es", "is"), ("un", "a"),
                 ("ejemplo", "example"), ("glosado", "glossed")):
        assert o in obj and g in gloss, f"missing {o}/{g} in example (4)"
        assert abs(obj[o] - gloss[g]) < 2.0, f"{o!r} is not above {g!r}"


@soffice
def test_nothing_overflows_the_right_margin(pdf: Path) -> None:
    xml = subprocess.run(["pdftotext", "-bbox", str(pdf), "-"],
                         check=True, capture_output=True, text=True).stdout
    ns = {"x": "http://www.w3.org/1999/xhtml"}
    for n, page in enumerate(ET.fromstring(xml).findall(".//x:page", ns), 1):
        width = float(page.get("width"))
        words = page.findall(".//x:word", ns)
        if not words:
            continue
        rightmost = max(float(w.get("xMax")) for w in words)
        assert rightmost <= width - 2 * CM + 2, f"page {n} overflows the margin"


@soffice
def test_numbers_come_from_the_formula_not_the_cached_value(
    converted: Path, tmp_path: Path
) -> None:
    """The strong form of the previous test.

    We emit a *correct* cached value inside each field, so a renderer that
    merely echoes it still shows the right number — which means the test
    above cannot distinguish a live field from dead text.  Here every
    cached value is corrupted to 99 before rendering: getting 1..12 back
    is only possible if LibreOffice evaluated ``ooow:NumEx+1`` itself.
    """
    content = postprocess.read(converted, "content.xml")
    corrupted = re.sub(
        r'(<text:sequence [^>]*text:name="NumEx"[^>]*>)\d+(</text:sequence>)',
        r"\g<1>99\g<2>",
        content,
    )
    assert corrupted != content, "no cached sequence values were found to corrupt"

    odt = tmp_path / "corrupted.odt"
    postprocess.rewrite(converted, odt, {"content.xml": corrupted})
    subprocess.run(
        ["soffice", "--headless", f"-env:UserInstallation=file://{tmp_path}/.lo",
         "--convert-to", "pdf", "--outdir", str(tmp_path), str(odt)],
        check=True, capture_output=True, timeout=240,
    )
    text = subprocess.run(
        ["pdftotext", "-layout", str(tmp_path / "corrupted.pdf"), "-"],
        check=True, capture_output=True, text=True,
    ).stdout
    assert "(99)" not in text, "the cached value was echoed; the field is not live"
    for n in range(1, 13):
        assert f"({n})" in text


@soffice
def test_overlong_example_is_split_into_aligned_bands(pdf: Path) -> None:
    """Example (11) of demo.tex is deliberately too wide for the text block.

    It must come out as stacked bands — each band a tier-row group starting
    back at the left edge — with every gloss still directly under its word.
    That is the pattern item 4 of tests/reference/reference.odt specifies.
    """
    words = _words(pdf)
    rows: dict[float, list[tuple[float, str]]] = {}
    for t, x, y in words:
        rows.setdefault(round(y), []).append((x, t))

    start = next(y for y in sorted(rows) if any(t == "Este" for _, t in rows[y]))
    ys = [y for y in sorted(rows) if y >= start][:4]
    band1_obj, band1_gloss, band2_obj, band2_gloss = (sorted(rows[y]) for y in ys)

    # the second band exists at all, and restarts at the left text edge
    assert band2_obj and band2_obj[0][1] == "que", "example (11) was not split"
    left = [x for x, t in band1_obj if not t.startswith("(")][0]
    assert abs(band2_obj[0][0] - left) < 1.0, "a continuation band is not left-aligned"

    # the number is on the first band only
    assert not any(t.startswith("(1") for _, t in band2_obj)

    for obj, gloss in ((band1_obj, band1_gloss), (band2_obj, band2_gloss)):
        pairs = [p for p in obj if not p[1].startswith("(")]
        assert len(pairs) == len(gloss), "a band lost a word or a gloss"
        for (ox, ot), (gx, gt) in zip(pairs, gloss):
            assert abs(ox - gx) < 2.0, f"{ot!r} is not above {gt!r}"


@pandoc
def test_judgment_marks_are_right_aligned_in_their_column(converted: Path) -> None:
    """Cosmetic, but silently lost if the cell style regresses: the mark
    hangs at the right edge of its column so it sits snug against the text
    it judges, the way linguexx \\llap's it."""
    content = postprocess.read(converted, "content.xml")
    styles = postprocess.read(converted, "styles.xml")

    judged = re.findall(
        r'<text:p text:style-name="(\w+)">'
        r'<text:span text:style-name="LxJudgment">',
        content,
    )
    assert judged, "no judgment mark found in the demo output"
    assert set(judged) == {"LxJudgmentCell"}, f"judgment cells use {set(judged)}"

    style = re.search(
        r'<style:style style:name="LxJudgmentCell".*?</style:style>', styles, re.S
    )
    assert style and 'fo:text-align="end"' in style.group(0)


@soffice
def test_sub_example_letters_align_with_main_example_text(pdf: Path) -> None:
    """linguexx's own geometry, measured from a pdflatex build of
    ../linguexx/tests/_preamble: a sub-example letter sits at exactly the x
    where a main example's *text* begins (both 3.72cm there), and a
    judgment mark hangs to the left of that.

    This is what forces the judgment column to be carved out of the column
    to its left instead of inserted after it: inserting it pushes the main
    example's text right while leaving the letters behind.
    """
    words = _words(pdf)
    first = {}
    for text, x, _y in sorted(words, key=lambda w: (w[2], w[1])):
        first.setdefault(text, x)

    main_text = first["This"]          # (1) "This is a first example."
    for letter in ("a.", "b."):
        assert abs(first[letter] - main_text) < 3.0, (
            f"sub-example letter {letter!r} at {first[letter]} does not line up "
            f"with the main example text at {main_text}"
        )

    assert first["*This"] < main_text, "the judgment mark does not hang to the left"
