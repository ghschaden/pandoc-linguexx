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

"""Drive LinguExx.bas inside a real LibreOffice and measure what it built.

The macro is installed from source into a throwaway profile and invoked
through the script provider, so what is tested is the file that ships —
not a Python re-implementation of it.

    python3 tools/run_macro_test.py [OUTDIR]
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

import uno  # type: ignore
from com.sun.star.beans import PropertyValue  # type: ignore
from com.sun.star.connection import NoConnectException  # type: ignore
from com.sun.star.text.ControlCharacter import PARAGRAPH_BREAK  # type: ignore

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))      # the shared PDF-reading helper
sys.path.insert(0, str(ROOT / "src"))

import pdfwords  # noqa: E402
from linguexx2odt import postprocess, writermacro  # noqa: E402

SOURCE = writermacro.path()
PORT = 2084


def connect(profile: Path, timeout: float = 45.0):
    subprocess.Popen(
        ["soffice", "--norestore", "--headless",
         f"-env:UserInstallation=file://{profile}",
         f"--accept=socket,host=localhost,port={PORT};urp;"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", local)
    deadline = time.time() + timeout
    while True:
        try:
            return resolver.resolve(
                f"uno:socket,host=localhost,port={PORT};urp;StarOffice.ComponentContext")
        except NoConnectException:
            if time.time() > deadline:
                raise
            time.sleep(0.5)


def install(ctx) -> None:
    """Put LinguExx.bas into the profile's Basic, exactly as My Macros holds it."""
    libs = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.script.ApplicationScriptLibraryContainer", ctx)
    if libs.hasByName("LinguExx"):
        libs.removeLibrary("LinguExx")
    libs.createLibrary("LinguExx")
    lib = libs.getByName("LinguExx")
    lib.insertByName("Gloss", writermacro.source())
    libs.storeLibraries()


def run(ctx, macro: str = "GlossSelectionQuiet") -> str:
    """Invoke the macro and return whatever it wanted to tell the user."""
    factory = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.script.provider.MasterScriptProviderFactory", ctx)
    script = factory.createScriptProvider("").getScript(
        f"vnd.sun.star.script:LinguExx.Gloss.{macro}?language=Basic&location=application")
    return script.invoke((), (), ())[0] or ""


def make_doc(ctx, lines: list[str]):
    desktop = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.frame.Desktop", ctx)
    doc = desktop.loadComponentFromURL("private:factory/swriter", "_blank", 0, ())
    text = doc.getText()
    text.setString("")
    cur = text.createTextCursor()
    for i, line in enumerate(lines):      # real paragraphs, as a user would type
        if i:
            text.insertControlCharacter(cur, PARAGRAPH_BREAK, False)
        text.insertString(cur, line, False)
    # select every line, the way a user would before invoking the macro
    cursor = doc.getCurrentController().getViewCursor()
    cursor.gotoRange(text.getStart(), False)
    cursor.gotoRange(text.getEnd(), True)
    return doc


words_of = pdfwords.words


def render(profile: Path, odt: Path) -> Path:
    subprocess.run(
        ["soffice", "--headless", f"-env:UserInstallation=file://{profile}-r",
         "--convert-to", "pdf", "--outdir", str(odt.parent), str(odt)],
        check=True, capture_output=True, timeout=240)
    return odt.with_suffix(".pdf")


CASES = {
    "plain": [
        "Esto es un ejemplo glosado",
        "this is a example glossed",
        "'This is a glossed example.'",
    ],
    "judged": [
        "*Das kleine Kind schlafen",
        "the little child sleep.INF",
        "'The little child sleeps.'",
    ],
    "braces": [
        "Ich {habe geschlafen}",
        "I {have slept}",
        "'I slept.'",
    ],
    "three_tiers": [
        "Ich habe geschlafen",
        "ich hab-e schlaf-en",
        "1SG have-1SG sleep-PTCP",
        "'I slept.'",
    ],
    "long": [
        "Este es un ejemplo mucho mas largo que no cabe en una sola linea de texto",
        "this is a example much more long that not fits in a single line of text",
        "'This is a much longer example that does not fit on one line.'",
    ],
}


PAIR = [
    "*Das kleine Kind schlafen",
    "the little child sleep.INF",
    "'The little child sleeps.'",
    "Das kleine Kind schlaeft",
    "the little child sleeps",
    "'The little child sleeps.'",
]


def paragraphs(doc):
    out, it = [], doc.getText().createEnumeration()
    while it.hasMoreElements():
        out.append(it.nextElement())
    return out


def check_pair(ctx, out: Path, profile: Path) -> int:
    """Two examples, one judged and one not, in a single document.

    This is the invariant the hanging judgment column exists for, the same
    one ../linguexx/tests/judgment-align.tex pins: the text block starts at
    the same x whether or not a mark precedes it.  It also proves the
    number field really is a sequence — the second example must be (2).
    """
    doc = make_doc(ctx, PAIR)
    # bottom example first, so building it cannot shift the paragraphs above
    for lo, hi in ((3, 5), (0, 2)):
        paras = [p for p in paragraphs(doc)
                 if p.supportsService("com.sun.star.text.Paragraph")]
        vc = doc.getCurrentController().getViewCursor()
        vc.gotoRange(paras[lo].getStart(), False)
        vc.gotoRange(paras[hi].getEnd(), True)
        msg = run(ctx)
        if msg:
            print(f"pair: MACRO SAID {msg!r}")
            doc.dispose()
            return 1
    odt = out / "pair.odt"
    doc.storeToURL(odt.as_uri(), (PropertyValue("FilterName", 0, "writer8", 0),))
    doc.dispose()

    words = words_of(render(profile, odt))
    text = " ".join(t for t, _x, _y in words)
    first = {}
    for t, x, y in sorted(words, key=lambda w: (w[2], w[1])):
        first.setdefault(t, x)

    print("--- pair")
    for t, x, _y in sorted(words, key=lambda w: (w[2], w[1]))[:4]:
        print(f"    {t!r} at x={x:.1f}")
    bad = 0
    if "(2)" not in text:
        print("    FAIL: the second example did not number itself (2)")
        bad += 1
    # 'kleine' is the second word of both; it starts the text block's second
    # column, which is unaffected by pdftotext merging the mark into 'Das'
    xs = [x for t, x, _y in words if t == "kleine"]
    if len(xs) != 2:
        print(f"    FAIL: expected 'kleine' twice, got {len(xs)}")
        bad += 1
    elif abs(xs[0] - xs[1]) > 1.0:
        print(f"    FAIL: a judgment mark shifted the text block: {xs}")
        bad += 1
    if not bad:
        print(f"    ok — judged and unjudged text both at x={xs[0]:.1f}")
    return bad


# Sub-example paradigms: one number, one shared column grid, one marker
# column.  (n_markers, glossed) is what each must come out as.
SUB_CASES = {
    "sub_plain": (["a. Sentences like this are fine.",
                   "b. Sentences like this are not."], 2, False),
    "sub_glossed": (["a. Esto es un ejemplo", "this is a example",
                     "'This is an example.'", "b. Otro ejemplo aqui",
                     "another example here", "'Another example here.'"], 2, True),
    "sub_judged": (["a. *Das kleine Kind schlafen", "the little child sleep.INF",
                    "b. Das kleine Kind schlaeft", "the little child sleeps"], 2, True),
    "sub_mixed": (["a. Esto es un ejemplo", "this is a example",
                   "b. This one is not glossed at all."], 2, True),
    "sub_roman": (["i. Otro ejemplo aqui", "another example here",
                   "ii. Tercer ejemplo aqui", "third example here"], 2, True),
    "sub_marker_alone": (["a.", "Esto es un ejemplo", "this is a example",
                          "b.", "Otro ejemplo aqui", "another example here"], 2, True),
}

# Selections the macro must refuse rather than mis-render, and near misses
# it must still accept.
REFUSE = {
    "marker_partway": ["Esto es un ejemplo", "this is a example",
                       "b. Otro ejemplo aqui", "another example here"],
}
ACCEPT = {
    "abbreviation": ["Dr. Meier kam gestern", "Dr. Meier came yesterday",
                     "'Dr Meier came yesterday.'"],
}

MARKER = re.compile(r"\(?[a-zA-Z]{1,4}[.)]$")


def check_sub(name: str, pdf: Path, n_markers: int, glossed: bool) -> int:
    """A sub-example paradigm: markers in their own column, one number.

    The markers must all sit at the same x, and each item's glosses must sit
    under its own words — the items share one column grid but each starts its
    own band at the left edge.
    """
    words = words_of(pdf)
    rows: dict[int, list[tuple[float, str]]] = {}
    for t, x, y in words:
        rows.setdefault(round(y), []).append((x, t))
    ys = sorted(rows)

    print(f"--- {name}")
    for y in ys:
        print("    " + "  ".join(f"{t}@{x:.1f}" for x, t in sorted(rows[y])))

    bad = 0
    text = " ".join(t for t, _x, _y in words)
    if text.count("(1)") != 1 or "(2)" in text:
        print("    FAIL: a paradigm must carry exactly one number")
        bad += 1

    marker_rows, marker_xs = [], []
    for y in ys:
        toks = sorted(rows[y])
        rest = [p for p in toks if not p[1].startswith("(")]
        if rest and MARKER.match(rest[0][1]):
            marker_rows.append(y)
            marker_xs.append(rest[0][0])
    if len(marker_xs) != n_markers:
        print(f"    FAIL: expected {n_markers} markers, found {len(marker_xs)}")
        bad += 1
    elif max(marker_xs) - min(marker_xs) > 1.0:
        print(f"    FAIL: markers are not in one column: {marker_xs}")
        bad += 1

    if glossed:
        for y in marker_rows:
            nxt = [z for z in ys if z > y]
            if not nxt:
                continue
            obj = [p for p in sorted(rows[y])
                   if not p[1].startswith("(") and not MARKER.match(p[1])]
            gloss = sorted(rows[nxt[0]])
            if len(obj) != len(gloss):
                continue          # an unglossed item inside the paradigm
            if obj and obj[0][1][0] in "*?#%!":
                obj, gloss = obj[1:], gloss[1:]      # mark merged by pdftotext
            for (ox, ot), (gx, gt) in zip(obj, gloss):
                if abs(ox - gx) > 2.0:
                    print(f"    FAIL: {ot!r} at {ox:.1f} not above {gt!r} at {gx:.1f}")
                    bad += 1
    if not bad:
        print(f"    ok — {len(marker_xs)} markers at x={marker_xs[0]:.1f}")
    return bad


def check_sub_alignment(ctx, out: Path, profile: Path) -> int:
    """A sub-example letter sits where a main example's *text* begins.

    linguexx's own geometry, and what forces the judgment column to be
    carved out of the column to its left rather than inserted after it.
    tests/test_e2e.py pins the same thing for the converter.
    """
    doc = make_doc(ctx, ["Esto es un ejemplo", "this is a example",
                         "a. Otro ejemplo aqui", "another example here"])
    for lo, hi in ((2, 3), (0, 1)):        # bottom first, so nothing shifts
        paras = [p for p in paragraphs(doc)
                 if p.supportsService("com.sun.star.text.Paragraph")]
        vc = doc.getCurrentController().getViewCursor()
        vc.gotoRange(paras[lo].getStart(), False)
        vc.gotoRange(paras[hi].getEnd(), True)
        msg = run(ctx)
        if msg:
            print(f"--- sub_alignment\n    FAIL: macro said {msg!r}")
            doc.dispose()
            return 1
    odt = out / "sub_alignment.odt"
    doc.storeToURL(odt.as_uri(), (PropertyValue("FilterName", 0, "writer8", 0),))
    doc.dispose()

    words = words_of(render(profile, odt))
    first = {}
    for t, x, y in sorted(words, key=lambda w: (w[2], w[1])):
        first.setdefault(t, x)
    print("--- sub_alignment")
    main_text, letter = first["Esto"], first["a."]
    print(f"    main example text at {main_text:.1f}, sub-example letter at {letter:.1f}")
    if abs(main_text - letter) > 3.0:
        print("    FAIL: the letter does not line up with a main example's text")
        return 1
    if first["Otro"] <= letter:
        print("    FAIL: sub-example text does not sit right of its letter")
        return 1
    print("    ok")
    return 0


# Long enough to be split into bands, with the translation written the way
# a linguexx user writes it: LaTeX's `quoted' convention.  Getting the quote
# wrong made the translation a third gloss tier, which put it inside the
# *first* band instead of at the end of the table, one word per column.
TRANSLATION_CASES = {
    "long_backtick": [
        "Ceci est un exemple superlong juste pour voir ce qui se passe quand on",
        "This is a example super_longue just for see what that SE happens when on",
        "`Juste pour voir\u2019",
    ],
    "curly_open": [
        "Esto es un ejemplo", "this is a example", "\u2018This is an example.\u2019",
    ],
    "guillemets": [
        "Esto es un ejemplo", "this is a example", "\u00abVoici un exemple\u00bb",
    ],
}


def check_translation_is_last(name: str, odt: Path) -> int:
    """The translation must be the last content row, whole, in one cell.

    Asserted on the ODT rather than the PDF: the failure mode is structural
    — a translation mistaken for a gloss tier still *renders*, it just
    renders in the wrong row, split across columns.
    """
    content = postprocess.read(odt, "content.xml")
    table = re.search(r"<table:table .*?</table:table>", content, re.S).group(0)
    body = re.findall(r"<table:table-row>.*?</table:table-row>", table, re.S)
    body = [r for r in body if "LxExampleSpace" not in r]

    print(f"--- {name}")
    bad = 0
    last = body[-1]
    if 'text:style-name="LxTranslation"' not in last:
        print("    FAIL: the last row is not the translation")
        bad += 1
    if any('text:style-name="LxTranslation"' in r for r in body[:-1]):
        print("    FAIL: a translation row appears before the end of the table")
        bad += 1
    cells = re.findall(r"<table:table-cell.*?</table:table-cell>", last, re.S)
    filled = [c for c in cells if re.sub(r"<[^>]+>", "", c).strip()]
    if len(filled) != 1:
        print(f"    FAIL: the translation is split across {len(filled)} cells")
        bad += 1
    if any(re.sub(r"<[^>]+>", "", r).count("Juste") > 0 for r in body[:-1]):
        print("    FAIL: translation text leaked into a gloss row")
        bad += 1
    if not bad:
        text = re.sub(r"<[^>]+>", "", last).strip()
        print(f"    ok — last row, one cell: {text[:46]!r}")
    return bad


# The commonest example there is: one line, no gloss.  (n content rows,
# translation expected)
PLAIN_CASES = {
    "single_line": (["A simple example."], 1, False),
    "single_translation": (["Un exemple simple", "'A simple example.'"], 2, True),
    "single_judged": (["*A bad example."], 1, False),
    "two_unglossed_translation": (["Un exemple simple", "`A simple example\u2019"], 2, True),
}


def check_plain_example(name: str, odt: Path, n_rows: int, translation: bool) -> int:
    """An unglossed example is running text in one cell, with a live number.

    Checked on the ODT: one word per column would still render, it would
    just be wrong, and at one word the difference is invisible in a PDF.
    """
    content = postprocess.read(odt, "content.xml")
    table = re.search(r"<table:table .*?</table:table>", content, re.S)
    print(f"--- {name}")
    if not table:
        print("    FAIL: no table was built")
        return 1
    rows = [r for r in re.findall(r"<table:table-row>.*?</table:table-row>",
                                 table.group(0), re.S)
            if "LxExampleSpace" not in r]
    bad = 0
    if len(rows) != n_rows:
        print(f"    FAIL: {len(rows)} content rows, expected {n_rows}")
        bad += 1
    if "<text:sequence " not in rows[0]:
        print("    FAIL: the first row carries no number field")
        bad += 1
    # Filled cells, less the number cell and the judgment cell — a judged
    # example legitimately has three.  What is left is the text, and it has
    # to be in exactly one cell rather than one word per column.
    filled = [re.sub(r"<[^>]+>", "", c).strip()
              for c in re.findall(r"<table:table-cell.*?</table:table-cell>", rows[0], re.S)
              if re.sub(r"<[^>]+>", "", c).strip()]
    text_cells = [c for c in filled
                  if not c.startswith("(") and c.strip("*?#%!") != ""]
    if len(text_cells) != 1:
        print(f"    FAIL: the line is in {len(text_cells)} cells, not one: {text_cells}")
        bad += 1
    if translation and 'text:style-name="LxTranslation"' not in rows[-1]:
        print("    FAIL: the translation is not the last row")
        bad += 1
    if not bad:
        print(f"    ok — {len(rows)} row(s), text in one cell: {text_cells[0][:40]!r}")
    return bad


def check_unglossed_alignment(ctx, out: Path, profile: Path) -> int:
    """An unglossed example must start where a glossed one starts.

    Otherwise a paper that mixes the two has its examples marching in and
    out by a few millimetres from one to the next.
    """
    doc = make_doc(ctx, ["Esto es un ejemplo", "this is a example",
                         "A simple unglossed example."])
    for lo, hi in ((2, 2), (0, 1)):        # bottom first, so nothing shifts
        paras = [p for p in paragraphs(doc)
                 if p.supportsService("com.sun.star.text.Paragraph")]
        vc = doc.getCurrentController().getViewCursor()
        vc.gotoRange(paras[lo].getStart(), False)
        vc.gotoRange(paras[hi].getEnd(), True)
        msg = run(ctx)
        if msg:
            print(f"--- unglossed_alignment\n    FAIL: macro said {msg!r}")
            doc.dispose()
            return 1
    odt = out / "unglossed_alignment.odt"
    doc.storeToURL(odt.as_uri(), (PropertyValue("FilterName", 0, "writer8", 0),))
    doc.dispose()

    first = {}
    for t, x, y in sorted(words_of(render(profile, odt)), key=lambda w: (w[2], w[1])):
        first.setdefault(t, x)
    print("--- unglossed_alignment")
    glossed, plain = first["Esto"], first["A"]
    print(f"    glossed text at {glossed:.1f}, unglossed text at {plain:.1f}")
    if abs(glossed - plain) > 1.0:
        print("    FAIL: the two kinds of example do not start at the same x")
        return 1
    if "(2)" not in " ".join(t for t, _x, _y in words_of(render(profile, odt))):
        print("    FAIL: the second example did not number itself (2)")
        return 1
    print("    ok")
    return 0


# An example wide enough to be split into two bands.  The point of the case
# is that the second band must lay itself out freely: with one rectangular
# grid shared by both, the fifth column of band 2 has to be as wide as the
# fifth column of band 1, so a long word in one line stretches an unrelated
# column in the other.
BANDED = [
    "Dies ist ein extrem langes Beispiel um zu zeigen, was passiert, "
    "wenn die Grenze einer Linie erst einmal \u00fcberschritten ist",
    "This is a extreme long example for to show what happens "
    "when the border a.gen line first once trespassed is",
    "`Just a test\u2019",
]


def check_bands(name: str, odt: Path, pdf: Path) -> int:
    content = postprocess.read(odt, "content.xml")
    table = re.search(r"<table:table .*?</table:table>", content, re.S).group(0)
    rows = [r for r in re.findall(r"<table:table-row>.*?</table:table-row>", table, re.S)
            if "LxExampleSpace" not in r]
    tiers = [r for r in rows if "LxTranslation" not in r]

    print(f"--- {name}")
    bad = 0
    if len(tiers) < 4:
        print(f"    FAIL: {len(tiers)} tier rows — the example did not split into bands")
        return bad + 1

    # The union grid is what makes the bands independent, and it is the only
    # thing that puts a span on a *tier* cell.  A rectangular grid never does.
    spans = [int(m) for r in tiers
             for m in re.findall(r'number-columns-spanned="(\d+)"', r)]
    if not any(sp > 1 for sp in spans):
        print("    FAIL: no tier cell spans more than one column — the bands "
              "are sharing one rectangular grid")
        bad += 1

    # and every gloss still sits under its own word, in every band
    by_y = sorted(rows_of(pdf).items())
    for band in range(len(tiers) // 2):
        obj = [p for p in by_y[band * 2][1] if not p[1].startswith("(")]
        gloss = by_y[band * 2 + 1][1]
        if len(obj) != len(gloss):
            print(f"    FAIL: band {band + 1}: {len(obj)} words over {len(gloss)} glosses")
            bad += 1
            continue
        for (ox, ot), (gx, gt) in zip(obj, gloss):
            if abs(ox - gx) > 2.0:
                print(f"    FAIL: band {band + 1}: {ot!r} at {ox:.1f} "
                      f"not above {gt!r} at {gx:.1f}")
                bad += 1
    if not bad:
        cols = table.count("<table:table-column")
        print(f"    ok — {len(tiers) // 2} bands, {cols} union columns, "
              f"widest span {max(spans)}")
    return bad


def rows_of(pdf: Path):
    out: dict[int, list[tuple[float, str]]] = {}
    for t, x, y in words_of(pdf):
        out.setdefault(round(y), []).append((x, t))
    for r in out.values():
        r.sort()
    return out


def check_guards(ctx) -> int:
    bad = 0
    for name, lines in REFUSE.items():
        doc = make_doc(ctx, lines)
        msg = run(ctx)
        tables = doc.getTextTables().getCount()
        doc.dispose()
        if not msg or tables:
            print(f"--- {name}\n    FAIL: built {tables} table(s), said {msg!r}")
            bad += 1
        else:
            print(f"--- {name}\n    ok — refused, nothing built")
    for name, lines in ACCEPT.items():
        doc = make_doc(ctx, lines)
        msg = run(ctx)
        tables = doc.getTextTables().getCount()
        doc.dispose()
        if msg or tables != 1:
            print(f"--- {name}\n    FAIL: refused a valid example ({msg!r})")
            bad += 1
        else:
            print(f"--- {name}\n    ok — not mistaken for a sub-example")
    return bad


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/lx-macro-test")
    out.mkdir(parents=True, exist_ok=True)
    profile = out / "profile"
    ctx = connect(profile)
    install(ctx)
    print(f"installed {SOURCE.name} into a throwaway profile\n")

    failures = 0
    for name, lines in CASES.items():
        doc = make_doc(ctx, lines)
        try:
            msg = run(ctx)
            if msg:
                print(f"{name}: MACRO SAID {msg!r}")
                failures += 1
        except Exception as exc:  # the macro raised: report and keep going
            print(f"{name}: MACRO ERROR {exc}")
            failures += 1
            doc.dispose()
            continue
        print(f"--- {name}", flush=True)
        odt = out / f"{name}.odt"
        doc.storeToURL(odt.as_uri(),
                       (PropertyValue("FilterName", 0, "writer8", 0),))
        doc.dispose()
        pdf = render(profile, odt)
        failures += check(name, lines, pdf)
    for name, (lines, n_markers, glossed) in SUB_CASES.items():
        doc = make_doc(ctx, lines)
        msg = run(ctx)
        if msg:
            print(f"--- {name}\n    FAIL: macro said {msg!r}")
            failures += 1
            doc.dispose()
            continue
        odt = out / f"{name}.odt"
        doc.storeToURL(odt.as_uri(), (PropertyValue("FilterName", 0, "writer8", 0),))
        doc.dispose()
        failures += check_sub(name, render(profile, odt), n_markers, glossed)
    failures += check_pair(ctx, out, profile)
    failures += check_sub_alignment(ctx, out, profile)
    for name, lines in TRANSLATION_CASES.items():
        doc = make_doc(ctx, lines)
        msg = run(ctx)
        odt = out / f"{name}.odt"
        doc.storeToURL(odt.as_uri(), (PropertyValue("FilterName", 0, "writer8", 0),))
        doc.dispose()
        if msg:
            print(f"--- {name}\n    FAIL: macro said {msg!r}")
            failures += 1
            continue
        failures += check_translation_is_last(name, odt)
    for name, (lines, n_rows, translation) in PLAIN_CASES.items():
        doc = make_doc(ctx, lines)
        msg = run(ctx)
        odt = out / f"{name}.odt"
        doc.storeToURL(odt.as_uri(), (PropertyValue("FilterName", 0, "writer8", 0),))
        doc.dispose()
        if msg:
            print(f"--- {name}\n    FAIL: macro said {msg!r}")
            failures += 1
            continue
        failures += check_plain_example(name, odt, n_rows, translation)
    failures += check_unglossed_alignment(ctx, out, profile)

    doc = make_doc(ctx, BANDED)
    msg = run(ctx)
    odt = out / "banded.odt"
    doc.storeToURL(odt.as_uri(), (PropertyValue("FilterName", 0, "writer8", 0),))
    doc.dispose()
    if msg:
        print(f"--- banded\n    FAIL: macro said {msg!r}")
        failures += 1
    else:
        failures += check_bands("banded", odt, render(profile, odt))
    failures += check_guards(ctx)
    print("\nOK" if not failures else f"\n{failures} FAILURE(S)")
    return 1 if failures else 0


def check(name: str, lines: list[str], pdf: Path) -> int:
    words = words_of(pdf)
    rows: dict[int, list[tuple[float, str]]] = {}
    for t, x, y in words:
        rows.setdefault(round(y), []).append((x, t))
    ys = sorted(rows)
    text = " ".join(t for t, _x, _y in words)

    bad = 0
    for y in ys:
        print("    " + " ".join(t for _x, t in sorted(rows[y])))

    if "(1)" not in text:
        print("    FAIL: the number field did not render")
        bad += 1

    # Every gloss must sit under its word.  A judgment mark hangs snug
    # against the text it judges, so pdftotext merges it into the following
    # token ("*Das") and reports that token's xMin at the mark — the same
    # artefact tests/test_e2e.py works around.  The mark hanging *left* is
    # the invariant; the word behind it is checked from the second word on.
    obj = [(x, t) for x, t in sorted(rows[ys[0]]) if not t.startswith("(")]
    gloss = sorted(rows[ys[1]])
    judged = bool(obj) and obj[0][1][0] in "*?#%!"
    if len(obj) != len(gloss):
        print(f"    FAIL: {len(obj)} words over {len(gloss)} glosses")
        bad += 1
    else:
        if judged:
            if obj[0][0] >= gloss[0][0]:
                print(f"    FAIL: the judgment mark does not hang left "
                      f"({obj[0][0]:.1f} >= {gloss[0][0]:.1f})")
                bad += 1
            obj, gloss = obj[1:], gloss[1:]
        for (ox, ot), (gx, gt) in zip(obj, gloss):
            if abs(ox - gx) > 2.0:
                print(f"    FAIL: {ot!r} at {ox:.1f} is not above {gt!r} at {gx:.1f}")
                bad += 1
    if not bad:
        print("    ok")
    return bad


if __name__ == "__main__":
    raise SystemExit(main())
