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

import os
import re
import socket
import subprocess
import sys
import time
import zipfile
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

CASEMAP_NONE = 0                             # com.sun.star.style.CaseMap
SMALLCAPS = 4

#: every instance connect() started, so shutdown() can stop all of them
INSTANCES: list = []


def free_port() -> int:
    "A port nothing is listening on."
    # Deliberately not a fixed one.  A soffice left over from an earlier
    # run still owning the port answers the connection, and then the suite
    # drives whatever library *that* instance happens to hold rather than
    # the one just installed.  That has already produced a false failure
    # once, and it is how one run leaves strays for the next to trip over.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def connect(profile: Path, timeout: float = 45.0):
    port = free_port()
    proc = subprocess.Popen(
        ["soffice", "--norestore", "--headless",
         f"-env:UserInstallation=file://{profile}",
         f"--accept=socket,host=localhost,port={port};urp;"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", local)
    deadline = time.time() + timeout
    while True:
        try:
            ctx = resolver.resolve(
                f"uno:socket,host=localhost,port={port};urp;"
                "StarOffice.ComponentContext")
            INSTANCES.append((proc, ctx))
            return ctx
        except NoConnectException:
            if proc.poll() is not None:
                # from None: the NoConnectException is the symptom, not
                # the cause.  soffice is already dead, and chaining its
                # refusal to connect buries the returncode that says why.
                raise RuntimeError(
                    f"soffice exited with {proc.returncode} before it "
                    f"accepted a connection on port {port}") from None
            if time.time() > deadline:
                proc.kill()
                raise
            time.sleep(0.5)


def shutdown() -> None:
    "Stop everything connect() started, so nothing outlives the run."
    while INSTANCES:
        proc, ctx = INSTANCES.pop()
        try:
            ctx.ServiceManager.createInstanceWithContext(
                "com.sun.star.frame.Desktop", ctx).terminate()
        except Exception:            # already gone, or the bridge is down
            pass
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()


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


def run(ctx, macro: str = "GlossSelectionQuiet", args: tuple = ()) -> str:
    """Invoke the macro and return whatever it wanted to tell the user."""
    factory = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.script.provider.MasterScriptProviderFactory", ctx)
    script = factory.createScriptProvider("").getScript(
        f"vnd.sun.star.script:LinguExx.Gloss.{macro}?language=Basic&location=application")
    return script.invoke(tuple(args), (), ())[0] or ""


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
        # a line is a plain string, or [(text, small_caps), ...] for one the
        # linguist formatted by hand
        for part, small_caps in [(line, False)] if isinstance(line, str) else line:
            cur.CharCaseMap = SMALLCAPS if small_caps else CASEMAP_NONE
            text.insertString(cur, part, False)
        cur.CharCaseMap = CASEMAP_NONE
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
    # A judgment mark typed straight after the letter, with no space to
    # split on.  The whole first word is then "b.?Maybe", which is not a
    # marker, so the line stopped starting an item: it was folded into the
    # item before it as another gloss tier and a paradigm of judged
    # one-liners came out as a single word-by-word grid.
    "sub_judged_glued": (["a.*This one is bad.",
                          "b.?Maybe this one is fine."], 2, False),
    # The same, mixed with the spaced form — the shape tests/subexamples_
    # judged.odt holds.  Here the first line *was* read as a marker, so the
    # selection looked like a paradigm and only the glued line went astray.
    "sub_judged_half_glued": (["a. *This one is bad.",
                               "b.?Maybe this one is fine.",
                               "c. ?Probably not though."], 3, False),
    # Writer's French autocorrect replaces the space before a "?" with a
    # narrow no-break one, and nothing on screen shows which is which.  It
    # was not a space to the word splitter, so the marker fused to the text
    # after it; a glossed item must still line its tiers up.  The unglossed
    # half of this is check_autocorrect_spaces, which has to read the table
    # rather than the PDF.
    "sub_judged_nnbsp": (["a.\u202f*Das Kind schlafen", "the child sleep.INF",
                          "b.\u202fDas Kind schlaeft", "the child sleeps"], 2, True),
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
    # A marker may be the head of the first word rather than the whole of
    # it, so that "b.?Maybe" is sub-example b — but only when a judgment
    # mark follows.  Anything else after the dot is part of the word.
    "dotted_word": ["Sie hat a.out gestartet", "she has a.out started",
                    "'She started a.out.'"],
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


# Two glossed items whose words are wildly unequal in width.  "Ich habe
# geschlafen" is short where "Der ausserordentlich lange Beispielsatz hier"
# is long, word for word.
OWN_COLUMNS = [
    "a. Ich habe geschlafen",
    "I have slept",
    "b. Der ausserordentlich lange Beispielsatz hier",
    "the extraordinarily long example.sentence here",
]


def check_items_keep_their_own_columns(ctx, out: Path, profile: Path) -> int:
    """A short glossed item must not be stretched by a longer one beside it.

    The items of a paradigm share one table, and they used to share one
    width per word index with it: item a's third column had to be as wide
    as item b's, so "Ich habe geschlafen" acquired a gap in the middle
    because "ausserordentlich" sits under "habe" in an unrelated sentence.
    The grid absorbs the difference now, exactly as it already did for the
    bands of a single item.  tests/test_bands.py pins the same thing for
    the converter.
    """
    doc = make_doc(ctx, OWN_COLUMNS)
    msg = run(ctx)
    odt = out / "own_columns.odt"
    doc.storeToURL(odt.as_uri(), (PropertyValue("FilterName", 0, "writer8", 0),))
    doc.dispose()
    print("--- own_columns")
    if msg:
        print(f"    FAIL: macro said {msg!r}")
        return 1

    first: dict[str, float] = {}
    for t, x, y in sorted(words_of(render(profile, odt)), key=lambda w: (w[2], w[1])):
        first.setdefault(t, x)
    short, wide = first["geschlafen"], first["lange"]
    print(f"    item a's third word at {short:.1f}, item b's at {wide:.1f}")
    if short >= wide - 10.0:
        print("    FAIL: the short item was stretched onto the long one's columns")
        return 1

    # and every gloss still sits under the word it glosses, in both items
    for obj, gloss in (("Ich", "I"), ("habe", "have"), ("geschlafen", "slept"),
                       ("Der", "the"), ("lange", "long")):
        if abs(first[obj] - first[gloss]) > 2.0:
            print(f"    FAIL: {gloss!r} at {first[gloss]:.1f} is not under "
                  f"{obj!r} at {first[obj]:.1f}")
            return 1
    print("    ok — each item keeps its own widths, glosses still aligned")
    return 0


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


# The layout dialog's five lengths: indent, number, marker, above, below.
# Each is deliberately different from its default and from the others, so a
# value read back into the wrong field cannot pass.
LAYOUT_CM = (0.9, 2.0, 1.4, 0.30, 0.45)
LAYOUT_DEFAULT_CM = (0.0, 1.1, 0.7, 0.18, 0.18)
LAYOUT_LINES = ["a. Esto es un ejemplo", "this is a example",
                "b. Otro ejemplo aqui", "another example here"]
PT_PER_CM = 72 / 2.54


def build_with_layout(ctx, out: Path, name: str, layout) -> tuple[Path, int]:
    """One paradigm built under `layout`, plus the table's own left margin."""
    doc = make_doc(ctx, LAYOUT_LINES)
    if layout is not None:
        msg = run(ctx, "LayoutSettingsQuiet", layout)
        if msg:
            doc.dispose()
            raise RuntimeError(f"LayoutSettingsQuiet said {msg!r}")
    msg = run(ctx)
    if msg:
        doc.dispose()
        raise RuntimeError(f"GlossSelectionQuiet said {msg!r}")
    margin = doc.getTextTables().getByIndex(0).LeftMargin
    odt = out / f"{name}.odt"
    doc.storeToURL(odt.as_uri(), (PropertyValue("FilterName", 0, "writer8", 0),))
    doc.dispose()
    return odt, margin


def spacing_of(ctx, above_cm: float, below_cm: float) -> tuple:
    """Set the two spacings on a fresh document and report what they became.

    Returns the macro's message and, for the above, below and parent
    styles in that order, (height in 1/100 mm, declares one of its own).
    The inheritance is half the contract: equal sides must stay on the
    parent so that one sidebar edit of LxExampleSpace still moves both.
    """
    doc = make_doc(ctx, ["Esto es un ejemplo", "this is a example"])
    msg = run(ctx, "LayoutSettingsQuiet", (0.0, 1.1, 0.7, above_cm, below_cm))
    styles = doc.getStyleFamilies().getByName("ParagraphStyles")
    got = []
    for name in ("LxExampleSpaceAbove", "LxExampleSpaceBelow", "LxExampleSpace"):
        style = styles.getByName(name)
        # .value, not str(): a PropertyState comes back as a uno.Enum, and
        # comparing one to a string is quietly false for ever
        got.append((style.ParaLineSpacing.Height,
                    style.getPropertyState("ParaLineSpacing").value == "DIRECT_VALUE"))
    doc.dispose()
    return msg, got


def check_layout_settings(ctx, out: Path, profile: Path) -> int:
    """The layout settings move exactly what they say they move.

    Measured as a difference between two builds of the same paradigm, one
    under the defaults and one under LAYOUT_CM, so nothing here depends on
    where an example happens to start — only on how far each setting moved
    it.  The two indents that are floors are set well above their floor, so
    the shift is the whole of the change:

        the number   by the example indent
        the letter   by that, plus the change in the number indent
        its text     by that, plus the change in the marker indent
    """
    print("--- layout_settings")
    bad = 0

    # a document that has never been touched answers with the defaults
    doc = make_doc(ctx, ["Esto es un ejemplo"])
    fresh = [float(v) for v in run(ctx, "LayoutQuiet").split(";")]
    doc.dispose()
    if any(abs(a - b) > 0.005 for a, b in zip(fresh, LAYOUT_DEFAULT_CM)):
        print(f"    FAIL: an untouched document reports {fresh}, "
              f"not the defaults {list(LAYOUT_DEFAULT_CM)}")
        bad += 1

    try:
        before, margin0 = build_with_layout(ctx, out, "layout_default", None)
        after, margin1 = build_with_layout(ctx, out, "layout_set", LAYOUT_CM)
    except RuntimeError as exc:
        print(f"    FAIL: {exc}")
        return bad + 1

    # and reports back what it was set to — and offers it in the dialog,
    # which is built here and shown nowhere, so a mistyped control property
    # or a field holding its neighbour's value is caught without a window
    # server to execute() in
    doc = make_doc(ctx, ["Esto es un ejemplo"])
    msg = run(ctx, "LayoutSettingsQuiet", LAYOUT_CM)
    got = [float(v) for v in run(ctx, "LayoutQuiet").split(";")]
    shown = [float(v) for v in run(ctx, "LayoutDialogQuiet").split(";")]
    doc.dispose()
    if msg or any(abs(a - b) > 0.005 for a, b in zip(got, LAYOUT_CM)):
        print(f"    FAIL: set {list(LAYOUT_CM)}, read back {got} ({msg!r})")
        bad += 1
    if any(abs(a - b) > 0.005 for a, b in zip(shown, LAYOUT_CM)):
        print(f"    FAIL: the dialog would offer {shown}, not {list(LAYOUT_CM)}")
        bad += 1

    # out of range is refused rather than clamped, and changes nothing
    doc = make_doc(ctx, ["Esto es un ejemplo"])
    msg = run(ctx, "LayoutSettingsQuiet", (0.0, 1.1, 0.7, 0.18, 99.0))
    left = [float(v) for v in run(ctx, "LayoutQuiet").split(";")]
    doc.dispose()
    if not msg:
        print("    FAIL: 99 cm of space below was accepted")
        bad += 1
    elif any(abs(a - b) > 0.005 for a, b in zip(left, LAYOUT_DEFAULT_CM)):
        print(f"    FAIL: a refused setting still changed something: {left}")
        bad += 1

    # the indented table is placed where it was told to be
    if abs(margin0) > 20:
        print(f"    FAIL: the default table has a left margin of {margin0}")
        bad += 1
    if abs(margin1 - LAYOUT_CM[0] * 1000) > 20:
        print(f"    FAIL: the table's left margin is {margin1}, "
              f"expected {LAYOUT_CM[0] * 1000:.0f}")
        bad += 1

    # and every column boundary moved by the sum of the settings before it
    want = {
        "(1)": LAYOUT_CM[0],
        "a.": LAYOUT_CM[0] + LAYOUT_CM[1] - LAYOUT_DEFAULT_CM[1],
        "Esto": LAYOUT_CM[0] + LAYOUT_CM[1] - LAYOUT_DEFAULT_CM[1]
                + LAYOUT_CM[2] - LAYOUT_DEFAULT_CM[2],
    }
    xs = []
    for odt in (before, after):
        first = {}
        for t, x, y in sorted(words_of(render(profile, odt)), key=lambda w: (w[2], w[1])):
            first.setdefault(t, x)
        xs.append(first)
    for token, cm in want.items():
        if token not in xs[0] or token not in xs[1]:
            print(f"    FAIL: {token!r} is not in both renderings")
            bad += 1
            continue
        moved = (xs[1][token] - xs[0][token]) / PT_PER_CM
        print(f"    {token!r} moved {moved:.2f} cm, expected {cm:.2f}")
        if abs(moved - cm) > 0.12:
            print(f"    FAIL: {token!r} moved {moved:.2f} cm, not {cm:.2f}")
            bad += 1

    # the spacings are the styles: unequal sides break away from the parent
    apart = [round(cm * 1000) for cm in LAYOUT_CM[3:]]
    msg, got = spacing_of(ctx, *LAYOUT_CM[3:])
    if msg:
        print(f"    FAIL: unequal spacing: macro said {msg!r}")
        bad += 1
    elif [h for h, _own in got[:2]] != apart or not all(o for _h, o in got[:2]):
        print(f"    FAIL: {LAYOUT_CM[3]}/{LAYOUT_CM[4]} cm came out as {got}, "
              f"expected each side to carry {apart[0]}/{apart[1]} of its own")
        bad += 1

    # and equal ones stay on the parent, for both children to inherit
    both = round(0.25 * 1000)
    msg, got = spacing_of(ctx, 0.25, 0.25)
    if msg:
        print(f"    FAIL: equal spacing: macro said {msg!r}")
        bad += 1
    elif got[2] != (both, True) or any(own for _h, own in got[:2]):
        print(f"    FAIL: equal sides came out as {got}, expected the parent "
              f"to carry {both} and both children to inherit it")
        bad += 1
    elif [h for h, _own in got[:2]] != [both, both]:
        print(f"    FAIL: the children do not inherit {both}: {got}")
        bad += 1

    if not bad:
        print("    ok — defaults, round trip, dialog, refusal, three indents "
              "and both spacings")
    return bad


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


# The same example twice: once with the Leipzig glosses in small caps, the
# way a linguist types them, and once as plain lowercase to measure against.
# Everything else about the two is identical, so any difference between the
# tables they produce is the small caps and nothing else.
SMALL_CAPS_LINES = [
    "Das kleine Kind schlief",
    [("the little child ", False), ("sleep.pst.3sg", True)],
    "'The little child slept.'",
]
PLAIN_GLOSS_LINES = [
    "Das kleine Kind schlief",
    "the little child sleep.pst.3sg",
    "'The little child slept.'",
]
# and once more in real capitals, which is what measuring small caps at full
# size would come to.  The three of them bracket the answer from both sides.
CAPS_GLOSS_LINES = [
    "Das kleine Kind schlief",
    "the little child SLEEP.PST.3SG",
    "'The little child slept.'",
]


# One word per kind of formatting, object line and gloss line, so that each
# can be followed through the macro on its own.  ("bold+italic" is here
# because a run is a *combination* of properties, not one of a list.)
FORMAT_OBJECT = [("der", "plain"), ("Kater", "italic"), ("schlief", "bold"),
                 ("sehr", "bold+italic"), ("tief", "underline"),
                 ("heute", "charstyle")]
FORMAT_GLOSS = [("the", "plain"), ("cat", "smallcaps"), ("slept", "subscript"),
                ("very", "superscript"), ("deep", "plain"), ("today", "plain")]

BOLD, NORMAL = 150.0, 100.0
UNDERLINE_SINGLE = 1


def set_format(cur, kind: str) -> None:
    from com.sun.star.awt.FontSlant import ITALIC, NONE  # type: ignore
    cur.CharPosture = ITALIC if kind in ("italic", "bold+italic") else NONE
    cur.CharWeight = BOLD if kind in ("bold", "bold+italic") else NORMAL
    cur.CharCaseMap = SMALLCAPS if kind == "smallcaps" else CASEMAP_NONE
    cur.CharUnderline = UNDERLINE_SINGLE if kind == "underline" else 0
    cur.CharEscapement = {"subscript": -33, "superscript": 33}.get(kind, 0)
    cur.CharEscapementHeight = 58 if "script" in kind else 100
    if kind == "charstyle":
        cur.CharStyleName = "LxLeipzig"
    else:
        cur.setPropertyToDefault("CharStyleName")


def char_format(obj) -> tuple:
    """The character formatting of a range, as the document reports it."""
    return (obj.CharPosture.value, obj.CharWeight, obj.CharCaseMap,
            obj.CharEscapement, obj.CharEscapementHeight, obj.CharUnderline,
            obj.CharStyleName)


def check_formatting_round_trip(ctx) -> int:
    """Every word comes out formatted exactly as it went in.

    Small caps are the reported case, but nothing about the fix is specific
    to them, and this is what says so: italic, bold, both at once,
    underline, sub- and superscript and a character style all go through
    the same path.  Asked of the document rather than of the XML or the
    PDF, and asked as a comparison against the source, so it cannot pass by
    agreeing with a wrong expectation written into the test.
    """
    desktop = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.frame.Desktop", ctx)
    doc = desktop.loadComponentFromURL("private:factory/swriter", "_blank", 0, ())

    style = doc.createInstance("com.sun.star.style.CharacterStyle")
    doc.getStyleFamilies().getByName("CharacterStyles").insertByName(
        "LxLeipzig", style)
    style.CharCaseMap = SMALLCAPS             # as linguexx2odt defines it

    text = doc.getText()
    text.setString("x")                       # LibreOffice drops the formatting
    text.setString("")                        # of the very first insertion
    cur = text.createTextCursor()
    lines = (FORMAT_OBJECT, FORMAT_GLOSS,
             [("'The cat slept very deeply today.'", "plain")])
    for i, line in enumerate(lines):
        if i:
            text.insertControlCharacter(cur, PARAGRAPH_BREAK, False)
        for j, (word, kind) in enumerate(line):
            if j:
                set_format(cur, "plain")
                text.insertString(cur, " ", False)
            set_format(cur, kind)
            text.insertString(cur, word, False)
        set_format(cur, "plain")

    # what each word looks like before.  Only the two gloss lines: the
    # translation repeats their words in plain text and would mask them.
    before = {}
    paras = [p for p in paragraphs(doc)
             if p.supportsService("com.sun.star.text.Paragraph")]
    for para in paras[:2]:
        it = para.createEnumeration()
        while it.hasMoreElements():
            portion = it.nextElement()
            # adjacent like-formatted words are one portion, so index by word
            for word in portion.getString().split():
                before[word] = char_format(portion)

    vc = doc.getCurrentController().getViewCursor()
    vc.gotoRange(text.getStart(), False)
    vc.gotoRange(text.getEnd(), True)
    msg = run(ctx)
    print("--- formatting_round_trip")
    if msg:
        print(f"    FAIL: macro said {msg!r}")
        doc.dispose()
        return 1

    after = {}
    table = doc.getTextTables().getByIndex(0)
    for name in table.getCellNames():
        cell = table.getCellByName(name)
        word = cell.getString().strip()
        if not word or word.startswith("("):
            continue
        cell_cur = cell.getText().createTextCursor()
        cell_cur.gotoStart(False)
        cell_cur.gotoEnd(True)
        after[word] = char_format(cell_cur)
    doc.dispose()

    bad = 0
    for word, kind in FORMAT_OBJECT + FORMAT_GLOSS:
        was, now = before.get(word), after.get(word)
        if now is None:
            print(f"    FAIL: {word!r} ({kind}) is not in the table at all")
            bad += 1
        elif was != now:
            print(f"    FAIL: {word!r} went in as {kind} {was} "
                  f"and came out {now}")
            bad += 1
    if not bad:
        print(f"    ok — {len(FORMAT_OBJECT) + len(FORMAT_GLOSS)} words, "
              "each unchanged: " +
              ", ".join(sorted({k for _w, k in FORMAT_OBJECT + FORMAT_GLOSS})))
    return bad


# Bracket notation -> a drawn tree.  (source, labelled nodes, branches)
TREE_CASES = {
    "bracketed_leaves": ("[DP [D [the]] [NP [N [tree]]]]", 6, 5),
    "bare_leaves": ("[DP [D the] [NP [N tree]]]", 6, 5),
    "deep": ("[CP [C that] [TP [DP [D the] [NP [N cat]]] "
             "[T' [T -ed] [VP [V sleep]]]]]", 16, 15),
    "braced_label": ("[S [NP [D the] [N {long noisy constituent}]] [VP [V left]]]",
                     9, 8),
    "roof": ("[S [NP {the big tree, roof}] [VP [V slept]]]", 6, 5),
    "judged": ("*[S [NP him] [VP [V left]]]", 6, 5),
}

# Selections it must refuse rather than draw something wrong.
TREE_REFUSE = {
    "unclosed": "[DP [D the] [NP [N tree]]",
    "trailing_text": "[DP [D the]] rubbish",
    "not_a_tree": "DP D the",
    "unknown_option": "[S [NP {the tree, align=center}]]",
    "movement_arrow": "[CP [DP what] [TP [VP saw]]] \\draw(a)--(b)",
}


def check_trees(ctx) -> int:
    """Bracket notation comes out as a drawn tree, numbered like an example.

    Counts are the cheap part: what the numbers actually pin is that every
    node got a shape and every parent-child pair got a branch, which is
    what breaks if the first-child/next-sibling walk goes wrong.
    """
    print("--- trees")
    bad = 0
    for name, (src, nodes, branches) in TREE_CASES.items():
        doc = make_doc(ctx, [src])
        try:
            msg = run(ctx, "TreeSelectionQuiet")
        except Exception as exc:
            print(f"    FAIL: {name}: macro error {exc}")
            doc.dispose()
            bad += 1
            continue
        tables = doc.getTextTables().getCount()
        groups = doc.getDrawPage().getCount()
        pieces = doc.getDrawPage().getByIndex(0).getCount() if groups == 1 else -1
        content = doc.getTextTables().getByIndex(0).getCellByName("A2").getString() \
            if tables else ""
        doc.dispose()
        if msg:
            print(f"    FAIL: {name}: macro said {msg!r}")
            bad += 1
        elif tables != 1 or groups != 1:
            print(f"    FAIL: {name}: {tables} table(s), {groups} shape group(s)")
            bad += 1
        elif pieces != nodes + branches:
            print(f"    FAIL: {name}: {pieces} shapes in the group, "
                  f"expected {nodes} nodes + {branches} branches")
            bad += 1
        elif "1" not in content:
            print(f"    FAIL: {name}: no number in the number cell ({content!r})")
            bad += 1
        else:
            print(f"    ok — {name}: {nodes} nodes, {branches} branches, numbered")

    for name, src in TREE_REFUSE.items():
        doc = make_doc(ctx, [src])
        msg = run(ctx, "TreeSelectionQuiet")
        built = doc.getTextTables().getCount() + doc.getDrawPage().getCount()
        doc.dispose()
        if not msg or built:
            print(f"    FAIL: {name}: built {built} thing(s), said {msg!r}")
            bad += 1
        else:
            print(f"    ok — {name}: refused, {msg.split('.')[0][:52]!r}")
    return bad


def check_tree_geometry(ctx) -> int:
    """The branches actually join the nodes, on tiers that are apart.

    Counting shapes does not see either failure: put a polygon shape's
    position before its PolyPolygon and the branches are all still there,
    2501 units away from the tree; collapse the tier spacing and every node
    is still there, on top of one another.  Both are caught here, by asking
    where the shapes are rather than how many.
    """
    src, tiers = "[DP [D the] [NP [N tree]]]", 4
    doc = make_doc(ctx, [src])
    msg = run(ctx, "TreeSelectionQuiet")
    print("--- tree_geometry")
    if msg:
        print(f"    FAIL: macro said {msg!r}")
        doc.dispose()
        return 1

    group = doc.getDrawPage().getByIndex(0)
    nodes, branches = [], []
    for i in range(group.getCount()):
        shape = group.getByIndex(i)
        pos, size = shape.getPosition(), shape.getSize()
        box = (pos.X, pos.Y, pos.X + size.Width, pos.Y + size.Height)
        label = shape.getString() if hasattr(shape, "getString") else ""
        (nodes if label else branches).append(box)
    doc.dispose()

    bad = 0
    tol = 40                                  # 0.4 mm, more than a line width
    rows = sorted({round(b[1] / tol) for b in nodes})
    if len(rows) != tiers:
        print(f"    FAIL: nodes sit on {len(rows)} tiers, expected {tiers} — "
              "the tiers are not separated")
        bad += 1

    x0 = min(b[0] for b in nodes) - tol
    y0 = min(b[1] for b in nodes) - tol
    x1 = max(b[2] for b in nodes) + tol
    y1 = max(b[3] for b in nodes) + tol
    astray = [b for b in branches
              if b[0] < x0 or b[1] < y0 or b[2] > x1 or b[3] > y1]
    if astray:
        print(f"    FAIL: {len(astray)} branch(es) outside the tree, "
              f"first at {astray[0]} against nodes in "
              f"({x0}, {y0})-({x1}, {y1})")
        bad += 1
    else:
        # and each one reaches from the underside of a node to the top of one
        bottoms = [b[3] for b in nodes]
        tops = [b[1] for b in nodes]
        for b in branches:
            if min(abs(b[1] - v) for v in bottoms) > tol:
                print(f"    FAIL: a branch starts at y={b[1]}, "
                      "which is not the underside of any node")
                bad += 1
                break
            if min(abs(b[3] - v) for v in tops) > tol:
                print(f"    FAIL: a branch ends at y={b[3]}, "
                      "which is not the top of any node")
                bad += 1
                break
    if not bad:
        print(f"    ok — {len(nodes)} nodes on {tiers} tiers, "
              f"{len(branches)} branches all joining them")
    return bad


# Movement.  (lines, labelled nodes, branches, arrows) — an arrow is two
# shapes, the routed polyline and its head.
MOVE_CASES = {
    "wh": (["[CP [DP,name=wh what] [C' [C did] [TP [DP John] "
            "[VP [V see] [DP,name=t __]]]]]", "move t -> wh"], 14, 13, 1),
    "successive": (["[CP [DP,name=wh who] [C' [C did] [TP [DP,name=s2 __] "
                    "[VP [V leave] [DP,name=t2 __]]]]]",
                    "move t2 -> s2", "move s2 -> wh"], 14, 13, 2),
    "nested": (["[A [B,name=p x] [C [D,name=q y] [E,name=r z]]]",
                "move r -> q", "move q -> p"], 8, 7, 2),
}

MOVE_REFUSE = {
    "no_arrow": ["[S [NP,name=a x]]", "move a b"],
    "unknown_name": ["[S [NP,name=a x]]", "move a -> zzz"],
    "self_move": ["[S [NP,name=a x]]", "move a -> a"],
    "moves_only": ["move a -> b"],
    "tikz": ["[S [NP x]] \\draw[->] (a) to (b);"],
}


def shapes_of(group) -> dict:
    """The group's shapes, split by what they are.

    A branch is a LineShape, an arrow a PolyLineShape, and a
    PolyPolygonShape is a roof or an arrowhead depending on whether it is
    filled — so the drawing can be interrogated without counting on order.
    """
    out = {"nodes": [], "branches": [], "arrows": [], "heads": [],
           "roofs": [], "segments": []}
    for i in range(group.getCount()):
        shape = group.getByIndex(i)
        pos, size = shape.getPosition(), shape.getSize()
        box = (pos.X, pos.Y, pos.X + size.Width, pos.Y + size.Height)
        kind = shape.getShapeType().rsplit(".", 1)[-1]
        if kind == "TextShape":
            out["nodes"].append((shape.getString(), box))
        elif kind == "LineShape":
            out["branches"].append(box)
        elif kind == "PolyLineShape":
            out["arrows"].append(box)
            out["segments"] += segments_of(shape)
        elif kind == "PolyPolygonShape":
            filled = str(shape.FillStyle) != "NONE"
            out["heads" if filled else "roofs"].append(box)
            if filled:
                out["segments"] += segments_of(shape)
    return out


def segments_of(shape) -> list:
    """The shape's polygon as absolute segments.

    PolyPolygon reads back in its own coordinate frame, offset from the one
    getPosition() reports, so the offset is derived per shape by lining the
    polygon's own bounding box up with the shape's — no constant assumed.
    """
    pts = [(p.X, p.Y) for poly in shape.PolyPolygon for p in poly]
    if not pts:
        return []
    pos = shape.getPosition()
    dx = pos.X - min(x for x, _y in pts)
    dy = pos.Y - min(y for _x, y in pts)
    out = []
    for poly in shape.PolyPolygon:
        run = [(p.X + dx, p.Y + dy) for p in poly]
        out += list(zip(run, run[1:]))
    return out


def cuts_through(seg, box, tol: int = 25) -> bool:
    """Does an axis-aligned segment pass through a box, rather than touch it?

    The box is shrunk by `tol` first, so an arrow that stops exactly on a
    node's underside — which is the whole point — does not count as
    crossing it.
    """
    (ax, ay), (bx, by) = seg
    x0, y0, x1, y1 = box[0] + tol, box[1] + tol, box[2] - tol, box[3] - tol
    if x1 <= x0 or y1 <= y0:
        return False
    if abs(ax - bx) < 2:                                  # vertical
        return x0 < ax < x1 and min(ay, by) < y1 and max(ay, by) > y0
    if abs(ay - by) < 2:                                  # horizontal
        return y0 < ay < y1 and min(ax, bx) < x1 and max(ax, bx) > x0
    return False


def segments_cross(first, second) -> bool:
    """Do two segments properly cross — not merely touch at an endpoint?

    Branches are diagonal, so this cannot be the axis-aligned test
    cuts_through uses; an arrow meeting a branch exactly at a node's
    underside is contact, not a crossing.
    """
    def side(origin, a, b):
        return ((a[0] - origin[0]) * (b[1] - origin[1])
                - (a[1] - origin[1]) * (b[0] - origin[0]))

    p, q = first
    r, t = second
    d1, d2 = side(r, t, p), side(r, t, q)
    d3, d4 = side(p, q, r), side(p, q, t)
    eps = 1e-9
    return (((d1 > eps and d2 < -eps) or (d1 < -eps and d2 > eps))
            and ((d3 > eps and d4 < -eps) or (d3 < -eps and d4 > eps)))


# Tree shapes chosen to make an arrow work for its clearance: a landing
# site in the middle of the tree, a target whose sibling is far deeper,
# rightward movement, two arrows whose spans overlap, a roof in the way,
# and a target that dominates its own source.
CLEARANCE_CASES = {
    "from_the_right_edge": [
        "[CP [DP,name=w what] [C' [C did] [TP [DP John] "
        "[VP [V see] [DP,name=t __]]]]]", "move t -> w"],
    "landing_in_the_middle": [
        "[CP [C that] [TP [DP,name=s __] [VP [V left] [DP,name=t __]]]]",
        "move t -> s"],
    "target_with_a_deep_sibling": [
        "[S [A,name=a x] [B [C [D [E [F,name=f deep]]]]]]", "move f -> a"],
    "rightward": ["[S [A,name=a x] [B [C y] [D,name=d z]]]", "move a -> d"],
    "overlapping_spans": [
        "[S [A,name=p 1] [B,name=q 2] [C,name=r 3] [D,name=s 4]]",
        "move r -> p", "move s -> q"],
    "under_a_roof": [
        "[S [NP {the big tree, roof}] [VP [V,name=v left] [DP,name=t __]]]",
        "move t -> v"],
    "target_is_an_ancestor": [
        "[CP,name=top [C that] [TP [VP [V see] [DP,name=t __]]]]",
        "move t -> top"],
}


def check_arrow_clearance(ctx) -> int:
    """No arrow crosses anything — node, branch or roof.

    check_move_geometry tests arrows against node *boxes*; a branch is a
    diagonal and would slip through that.  The property holds for a
    structural reason rather than by luck: an arrow leaves and arrives at
    the underside of a whole subtree, so it never enters one, and sibling
    subtrees are laid out horizontally disjoint, so nothing else — node or
    branch — sits at a riser's x over the span it travels.  Structural or
    not, it is worth pinning: it was *not* true before arrows were moved
    off node baselines onto subtree undersides.
    """
    print("--- arrow_clearance")
    bad = 0
    for name, lines in CLEARANCE_CASES.items():
        doc = make_doc(ctx, lines)
        msg = run(ctx, "TreeSelectionQuiet")
        if msg:
            print(f"    FAIL: {name}: macro said {msg.splitlines()[0]!r}")
            doc.dispose()
            bad += 1
            continue
        group = doc.getDrawPage().getByIndex(0)
        parts = shapes_of(group)
        obstacles = []
        for i in range(group.getCount()):
            shape = group.getByIndex(i)
            kind = shape.getShapeType().rsplit(".", 1)[-1]
            roof = kind == "PolyPolygonShape" and str(shape.FillStyle) == "NONE"
            if kind == "LineShape" or roof:
                obstacles += segments_of(shape)
        doc.dispose()

        cut = [(a, b) for a in parts["segments"] for b in obstacles
               if segments_cross(a, b)]
        through = [t for seg in parts["segments"]
                   for t, box in parts["nodes"] if cuts_through(seg, box)]
        if cut:
            print(f"    FAIL: {name}: an arrow crosses a branch or roof at "
                  f"{cut[0][0]}")
            bad += 1
        elif through:
            print(f"    FAIL: {name}: an arrow passes through {through[0]!r}")
            bad += 1
        else:
            print(f"    ok — {name}: {len(parts['arrows'])} arrow(s) clear of "
                  f"{len(parts['nodes'])} nodes and {len(obstacles)} segments")
    return bad


def check_moves(ctx) -> int:
    """Movement arrows: named nodes, a move line, an arrow in the gutter."""
    print("--- moves")
    bad = 0
    for name, (lines, nodes, branches, arrows) in MOVE_CASES.items():
        doc = make_doc(ctx, lines)
        try:
            msg = run(ctx, "TreeSelectionQuiet")
        except Exception as exc:
            print(f"    FAIL: {name}: macro error {exc}")
            doc.dispose()
            bad += 1
            continue
        groups = doc.getDrawPage().getCount()
        parts = shapes_of(doc.getDrawPage().getByIndex(0)) if groups == 1 else None
        doc.dispose()
        if msg:
            print(f"    FAIL: {name}: macro said {msg!r}")
            bad += 1
        elif parts is None:
            print(f"    FAIL: {name}: {groups} groups")
            bad += 1
        elif (len(parts["nodes"]), len(parts["branches"]),
              len(parts["arrows"]), len(parts["heads"])) != \
                (nodes, branches, arrows, arrows):
            print(f"    FAIL: {name}: {len(parts['nodes'])} nodes, "
                  f"{len(parts['branches'])} branches, {len(parts['arrows'])} "
                  f"arrows, {len(parts['heads'])} heads; expected "
                  f"{nodes}/{branches}/{arrows}/{arrows}")
            bad += 1
        else:
            print(f"    ok — {name}: {arrows} arrow(s) over {nodes} nodes")

    for name, lines in MOVE_REFUSE.items():
        doc = make_doc(ctx, lines)
        msg = run(ctx, "TreeSelectionQuiet")
        built = doc.getTextTables().getCount() + doc.getDrawPage().getCount()
        doc.dispose()
        if not msg or built:
            print(f"    FAIL: {name}: built {built}, said {msg!r}")
            bad += 1
        else:
            print(f"    ok — {name}: refused, {msg.splitlines()[0][:48]!r}")
    return bad


def check_move_geometry(ctx) -> int:
    """The arrows run under the tree, in lanes, and point at the right nodes.

    Counting shapes would miss all three failures that matter: an arrow in
    the wrong coordinate frame is still an arrow, two arrows sharing a lane
    are still two arrows, and a head under the wrong node is still a head.
    The last one is the reason `name=` exists at all.
    """
    # unique labels on the named nodes, so a head can be tied to the node it
    # is supposed to point at rather than to "some node"
    lines = ["[CP [XP,name=wh who] [C' [C did] [TP [YP,name=s2 __] "
             "[VP [V leave] [ZP,name=t2 __]]]]]",
             "move t2 -> s2", "move s2 -> wh"]
    doc = make_doc(ctx, lines)
    msg = run(ctx, "TreeSelectionQuiet")
    print("--- move_geometry")
    if msg:
        print(f"    FAIL: macro said {msg!r}")
        doc.dispose()
        return 1
    parts = shapes_of(doc.getDrawPage().getByIndex(0))
    doc.dispose()

    bad = 0
    tol = 40
    node = {t: b for t, b in parts["nodes"]}
    node_bottom = max(b[3] for _t, b in parts["nodes"])
    if not {"XP", "YP", "ZP"} <= set(node):
        print(f"    FAIL: the named nodes are not in the drawing: {sorted(node)}")
        return bad + 1

    # every arrow's lane is below every node
    if any(box[3] < node_bottom for box in parts["arrows"]):
        print(f"    FAIL: an arrow ends above the deepest node at "
              f"y={node_bottom} — it is not in the gutter")
        bad += 1

    # the two arrows are in different lanes
    lanes = sorted(box[3] for box in parts["arrows"])
    if len(lanes) != 2:
        print(f"    FAIL: {len(lanes)} arrows, expected 2")
        return bad + 1
    if abs(lanes[0] - lanes[1]) < tol:
        print(f"    FAIL: both arrows run in the same lane ({lanes})")
        bad += 1

    # the heads point at the two *targets* — ZP is a source and never a
    # target, so a head over it means the arrow is drawn the wrong way round
    def centre(box):
        return (box[0] + box[2]) / 2

    want = sorted(round(centre(node[t])) for t in ("XP", "YP"))
    got = sorted(round(centre(b)) for b in parts["heads"])
    if any(abs(a - b) > tol for a, b in zip(want, got)) or len(want) != len(got):
        print(f"    FAIL: heads are centred at {got}, but the nodes moved to "
              f"(XP, YP) are at {want}")
        bad += 1

    # and each arrow reaches up to its own head: the polyline stops exactly
    # where the head begins.  Get the box origin wrong and the arrow sinks
    # away from its head while still looking like an arrow.
    head_bottoms = [b[3] for b in parts["heads"]]
    for box in parts["arrows"]:
        if min(abs(box[1] - v) for v in head_bottoms) > tol:
            print(f"    FAIL: an arrow's top is y={box[1]}, which is not the "
                  f"foot of any head ({[round(v) for v in head_bottoms]}) — "
                  "the arrow does not meet its own head")
            bad += 1
            break

    # and nothing an arrow is made of passes through a node.  An arrow
    # leaves and arrives at the underside of a whole subtree for exactly
    # this reason: aim at the node's own baseline instead and the riser goes
    # straight through whatever the node dominates.
    for seg in parts["segments"]:
        hit = [t for t, b in parts["nodes"] if cuts_through(seg, b)]
        if hit:
            print(f"    FAIL: an arrow segment {seg} passes through "
                  f"{hit[0]!r} — arrows must point at nodes, not cross them")
            bad += 1
            break

    if not bad:
        print(f"    ok — 2 arrows below y={node_bottom}, in lanes "
              f"{lanes[0]} and {lanes[1]}, each meeting a head on its "
              f"target, none crossing a node")
    return bad


def check_bare_tree(ctx, out: Path, profile: Path) -> int:
    """A tree with no number: no table, no example styles, just the drawing.

    The thing to pin beyond "it built" is that it still takes up room. An
    as-character group reserves vertical space in the line but not
    horizontal, so a bare tree has to push the paragraph after it down —
    and has to be told about when there is text left on its own line, which
    would end up beside it rather than after it.
    """
    print("--- bare_tree")
    bad = 0

    doc = make_doc(ctx, ["TEXTABOVE here", "[DP [D the] [NP [N tree]]]",
                         "TEXTBELOW here"])
    paras = [p for p in paragraphs(doc)
             if p.supportsService("com.sun.star.text.Paragraph")]
    vc = doc.getCurrentController().getViewCursor()
    vc.gotoRange(paras[1].getStart(), False)
    vc.gotoRange(paras[1].getEnd(), True)
    msg = run(ctx, "TreeSelectionBareQuiet")
    tables = doc.getTextTables().getCount()
    groups = doc.getDrawPage().getCount()
    anchor = pieces = None
    if groups == 1:
        group = doc.getDrawPage().getByIndex(0)
        anchor, pieces = str(group.AnchorType), group.getCount()
    odt = out / "bare_tree.odt"
    doc.storeToURL(odt.as_uri(), (PropertyValue("FilterName", 0, "writer8", 0),))
    doc.dispose()

    if msg:
        print(f"    FAIL: macro said {msg!r}")
        return 1
    if tables:
        print(f"    FAIL: {tables} table(s) — a bare tree builds none")
        bad += 1
    if groups != 1 or pieces != 11:
        print(f"    FAIL: {groups} group(s), {pieces} shapes, expected 1 and 11")
        bad += 1
    elif "AS_CHARACTER" not in anchor:
        print(f"    FAIL: the group is anchored {anchor}, not as a character")
        bad += 1

    words = words_of(render(profile, odt))
    ys = {t: y for t, _x, y in words}
    nodes = [y for t, _x, y in words if t in ("DP", "D", "NP", "N", "the", "tree")]
    if "TEXTBELOW" not in ys or not nodes:
        print(f"    FAIL: the page is not what was built: {sorted(ys)}")
        bad += 1
    elif max(nodes) >= ys["TEXTBELOW"] - 2.0:
        print(f"    FAIL: the tree runs to y={max(nodes):.0f} and the next "
              f"paragraph is at y={ys['TEXTBELOW']:.0f} — it reserved no room")
        bad += 1

    # a judgment mark has no column to hang in, so it is set as text
    doc = make_doc(ctx, ["*[S [NP him] [VP [V left]]]"])
    msg = run(ctx, "TreeSelectionBareQuiet")
    para = "".join(p.getString() for p in paragraphs(doc)
                   if p.supportsService("com.sun.star.text.Paragraph"))
    doc.dispose()
    if msg or para.strip() != "*":
        print(f"    FAIL: judged bare tree: text is {para.strip()!r}, "
              f"said {msg!r}")
        bad += 1

    # and it says so when something is left on the line after it
    doc = make_doc(ctx, ["as in [DP [D the] [NP [N tree]]] above."])
    paras = [p for p in paragraphs(doc)
             if p.supportsService("com.sun.star.text.Paragraph")]
    vc = doc.getCurrentController().getViewCursor()
    vc.gotoRange(paras[0].getStart(), False)
    vc.goRight(len("as in "), False)
    vc.goRight(len("[DP [D the] [NP [N tree]]]"), True)
    msg = run(ctx, "TreeSelectionBareQuiet")
    doc.dispose()
    if "last thing on its line" not in msg:
        print(f"    FAIL: no warning about the text after the tree: {msg!r}")
        bad += 1

    if not bad:
        print("    ok — no table, anchored as a character, reserves its room, "
              "warns about a tail")
    return bad


def check_tree_alignment(ctx, out: Path, profile: Path) -> int:
    """A tree begins where an example's text begins.

    The whole reason a tree is built into the same table as an example: in
    a document that mixes them they must not march in and out by a few
    millimetres.  Also pins that the long label is *not* broken over two
    lines, which is what measuring with getStringWidth instead of the
    probe shape did.
    """
    doc = make_doc(ctx, ["Esto es un ejemplo", "this is a example",
                         "[S [NP [D the] [N {long noisy constituent}]] [VP [V left]]]"])
    paras = [p for p in paragraphs(doc)
             if p.supportsService("com.sun.star.text.Paragraph")]
    vc = doc.getCurrentController().getViewCursor()
    vc.gotoRange(paras[2].getStart(), False)      # the tree first, bottom up
    vc.gotoRange(paras[2].getEnd(), True)
    msg = run(ctx, "TreeSelectionQuiet")
    if not msg:
        paras = [p for p in paragraphs(doc)
                 if p.supportsService("com.sun.star.text.Paragraph")]
        vc = doc.getCurrentController().getViewCursor()
        vc.gotoRange(paras[0].getStart(), False)
        vc.gotoRange(paras[1].getEnd(), True)
        msg = run(ctx)
    odt = out / "tree_alignment.odt"
    doc.storeToURL(odt.as_uri(), (PropertyValue("FilterName", 0, "writer8", 0),))
    doc.dispose()

    print("--- tree_alignment")
    if msg:
        print(f"    FAIL: macro said {msg!r}")
        return 1

    words = words_of(render(profile, odt))
    bad = 0
    example = min(x for t, x, _y in words if t == "Esto")
    tree_words = {"the", "long", "noisy", "constituent", "left", "D", "N", "V"}
    tree_left = min(x for t, x, _y in words if t in tree_words)
    print(f"    example text at {example:.1f}, tree at {tree_left:.1f}")
    if abs(example - tree_left) > 3.0:
        print("    FAIL: the tree does not start where the example's text does")
        bad += 1

    # the braced label must be one line, not wrapped inside its node box
    ys = {t: y for t, _x, y in words if t in ("long", "noisy", "constituent")}
    if len(ys) != 3:
        print(f"    FAIL: the braced label did not render whole: {ys}")
        bad += 1
    elif max(ys.values()) - min(ys.values()) > 2.0:
        print(f"    FAIL: the braced label wrapped inside its node: {ys}")
        bad += 1
    if not bad:
        print("    ok — aligned, and the braced label is on one line")
    return bad


def check_tree_formatting(ctx) -> int:
    """A node label keeps the formatting it was typed in.

    Free, in principle, because the label rides through the parser with its
    format marks on and the probe measures it by rendering it — but only if
    the parser really does treat a mark as part of the label rather than as
    structure.
    """
    doc = make_doc(ctx, [[("[DP [D the] [NP [N ", False), ("sg", True),
                          ("]]]", False)]])
    msg = run(ctx, "TreeSelectionQuiet")
    print("--- tree_formatting")
    if msg:
        print(f"    FAIL: macro said {msg!r}")
        doc.dispose()
        return 1
    group = doc.getDrawPage().getByIndex(0)
    found = {}
    for i in range(group.getCount()):
        shape = group.getByIndex(i)
        text = shape.getString() if hasattr(shape, "getString") else ""
        if not text:
            continue
        # the shape's own CharCaseMap is its default for new text and stays
        # 0; the run's formatting is on the text, so ask the text
        cur = shape.getText().createTextCursor()
        cur.gotoStart(False)
        cur.gotoEnd(True)
        found[text] = cur.CharCaseMap
    doc.dispose()

    bad = 0
    if "sg" not in found:
        print(f"    FAIL: the label is not in the tree as 'sg': {sorted(found)}")
        bad += 1
    elif found["sg"] != SMALLCAPS:
        print(f"    FAIL: 'sg' lost its small caps (CharCaseMap {found['sg']})")
        bad += 1
    if found.get("the", CASEMAP_NONE) != CASEMAP_NONE:
        print("    FAIL: an unformatted label picked up formatting")
        bad += 1
    if not bad:
        print("    ok — 'sg' still reads lowercase and is still small caps")
    return bad


def column_widths(odt: Path) -> list[float]:
    content = postprocess.read(odt, "content.xml")
    widths = dict(re.findall(
        r'<style:style style:name="([^"]+)" style:family="table-column">'
        r'<style:table-column-properties style:column-width="([\d.]+)cm"', content))
    return [float(widths[n]) for n in
            re.findall(r'<table:table-column table:style-name="([^"]+)"', content)]


def check_small_caps(ctx, out: Path, profile: Path) -> int:
    """Small caps a linguist applied by hand survive, and are measured.

    Two failures hide here, and only the first is visible by looking at the
    result.  The macro used to read the selection with getString(), so the
    formatting went in the bin and a gloss tier came out as lowercase prose.
    The second is what makes it a layout bug rather than a cosmetic one:
    small caps are capitals at 80% of the size, which is *wider* than the
    lowercase they replace, so a column measured on the lowercase is too
    narrow for what is put in it and the cell wraps.  Measuring them as
    full-size capitals is the other way to be wrong, so the width is pinned
    from both sides.
    """
    odts = {}
    for name, lines in (("small_caps", SMALL_CAPS_LINES),
                        ("plain_gloss", PLAIN_GLOSS_LINES),
                        ("caps_gloss", CAPS_GLOSS_LINES)):
        doc = make_doc(ctx, lines)
        msg = run(ctx)
        odts[name] = odt = out / f"{name}.odt"
        doc.storeToURL(odt.as_uri(), (PropertyValue("FilterName", 0, "writer8", 0),))
        doc.dispose()
        if msg:
            print(f"--- small_caps\n    FAIL: macro said {msg!r}")
            return 1

    print("--- small_caps")
    bad = 0

    # The text itself must be untouched — small caps are a way of drawing
    # letters, not a different set of letters.  Uppercasing the string would
    # pass the render check below and still be wrong.
    content = postprocess.read(odts["small_caps"], "content.xml")
    table = re.search(r"<table:table .*?</table:table>", content, re.S).group(0)
    if "sleep.pst.3sg" not in re.sub(r"<[^>]+>", "", table):
        print("    FAIL: the gloss no longer reads 'sleep.pst.3sg' in the file")
        bad += 1

    # ...but it must *render* as capitals, which is what small caps are.
    # Joined without the spaces, because a small capital is a size change
    # and pdftotext breaks a token at every one of them.
    pdf_words = [t for t, _x, _y in words_of(render(profile, odts["small_caps"]))]
    if "SLEEP.PST.3SG" not in "".join(pdf_words):
        print(f"    FAIL: the gloss did not render in small caps: {pdf_words}")
        bad += 1

    # And the column that holds it has to have been measured as small caps.
    # Only that one column may differ: the gloss is the widest thing in it,
    # and nothing else about the two examples changed.
    sc, plain = column_widths(odts["small_caps"]), column_widths(odts["plain_gloss"])
    if len(sc) != len(plain):
        print(f"    FAIL: {len(sc)} columns against {len(plain)} — "
              "the small caps changed the grid, not just a width")
        return bad + 1
    moved = [i for i, (a, b) in enumerate(zip(sc, plain)) if abs(a - b) > 0.01]
    # the trailing filler column absorbs whatever the others give up
    moved = [i for i in moved if i != len(sc) - 1]
    if len(moved) != 1:
        print(f"    FAIL: {len(moved)} columns changed width, expected 1: "
              f"{sc} against {plain}")
        bad += 1
    else:
        i = moved[0]
        caps = column_widths(odts["caps_gloss"])
        if not plain[i] < sc[i] < caps[i]:
            print(f"    FAIL: the small-caps column is {sc[i]}cm, outside the "
                  f"lowercase {plain[i]}cm .. capitals {caps[i]}cm it has to "
                  "sit between")
            bad += 1
        elif not bad:
            print(f"    ok — reads 'sleep.pst.3sg', renders 'SLEEP.PST.3SG', "
                  f"column {i} at {sc[i]}cm, between lowercase {plain[i]}cm "
                  f"and capitals {caps[i]}cm")
    return bad


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


# What a judged paradigm looks like when it is typed rather than pasted.
# Writer's autocorrect replaces the space before "?" and "!" with a
# no-break one under a French locale — narrow, in recent versions — and
# nothing on screen tells the two apart.
AUTOCORRECT_SPACES = {
    "nbsp": ("\u00a0", "no-break space"),
    "nnbsp": ("\u202f", "narrow no-break space"),
}


def check_autocorrect_spaces(ctx) -> int:
    """A space Writer substituted must still separate a marker from its text.

    Read off the table, not the PDF.  pdftotext prints a no-break space as
    a space, so a paradigm that was never parsed as one can still render
    close enough to fool a check that measures where the words landed —
    which is exactly what an earlier version of this test did.
    """
    bad = 0
    want = {"B2": "a.", "C2": "*", "D2": "This one is bad.",
            "B3": "b.", "C3": "?", "D3": "Maybe this one is fine."}
    for name, (space, what) in AUTOCORRECT_SPACES.items():
        doc = make_doc(ctx, [f"a.{space}*This one is bad.",
                             f"b.{space}?Maybe this one is fine."])
        msg = run(ctx)
        tables = doc.getTextTables()
        count = tables.getCount()
        got = {}
        if count == 1:
            table = tables.getByIndex(0)
            for cell in table.getCellNames():
                got[cell] = table.getCellByName(cell).getString()
        doc.dispose()
        wrong = {k: got.get(k) for k, v in want.items() if got.get(k) != v}
        print(f"--- autocorrect_{name}")
        if msg or count != 1:
            print(f"    FAIL: built {count} table(s), said {msg!r}")
            bad += 1
        elif wrong:
            print(f"    FAIL: a {what} did not separate the marker — {wrong}")
            bad += 1
        else:
            print(f"    ok — a {what} separates marker, mark and text")
    return bad


def cell_style(table, name: str) -> str:
    "The paragraph style of a table cell, or '' where a merge left no cell."
    try:
        return table.getCellByName(name).getText().createEnumeration(
            ).nextElement().ParaStyleName
    except Exception:
        return ""


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
        tables = doc.getTextTables()
        count = tables.getCount()
        # Where the judgment column landed says whether this was read as a
        # paradigm: it is the column before the text, so a marker column in
        # front of it moves it from B to C.  A table was always built either
        # way, which is why counting tables alone never caught this.
        columns = set()
        if count == 1:
            table = tables.getByIndex(0)
            for cell in table.getCellNames():
                if cell_style(table, cell) == "LxJudgmentCell":
                    columns.add(cell.rstrip("0123456789"))
        doc.dispose()
        if msg or count != 1:
            print(f"--- {name}\n    FAIL: refused a valid example ({msg!r})")
            bad += 1
        elif columns != {"B"}:
            print(f"--- {name}\n    FAIL: read as a paradigm — "
                  f"judgment column {sorted(columns)}, wanted ['B']")
            bad += 1
        else:
            print(f"--- {name}\n    ok — not mistaken for a sub-example")
    return bad


# A paradigm of trees, built by the numbered-tree command.  Every item is
# a tree because the command says so — nothing is read out of the brackets.
# (lines, trees drawn, markers)
TREE_ITEM_CASES = {
    "two_trees": (["a. [DP [D the] [NP [N tree]]]",
                   "b. [DP [D a] [NP [N cat]]]"], 2, 2),
    "three_trees": (["a. [DP [D the] [NP [N tree]]]",
                     "b. [DP [D a] [NP [N cat]]]",
                     "c. [VP [V sang] [AdvP [Adv loudly]]]"], 3, 3),
    "judged": (["a. *[S [NP him] [VP [V left]]]",
                "b. [S [NP he] [VP [V left]]]"], 2, 2),
    "with_translations": (["a. [DP [D the] [NP [N tree]]]", "'the tree'",
                           "b. [DP [D a] [NP [N cat]]]", "'a cat'"], 2, 2),
    "with_movement": (
        ["a. [CP [DP,name=w what] [TP [V saw] [DP,name=t __]]]",
         "move t -> w", "b. [CP [DP who] [TP [V left]]]"], 2, 2),
    "single_tree": (["[DP [D the] [NP [N tree]]]"], 1, 0),
    # The tree reader splits on the same spaces the word splitter does, so
    # a no-break one inside the brackets used to fuse a label to its leaf
    # and produce one node called "NP him" instead of NP over him.
    "nbsp_in_brackets": (["a.\u00a0*[S [NP\u00a0him] [VP [V left]]]",
                          "b. [S [NP he] [VP [V left]]]"], 2, 2),
}

# Typeset example must never draw a tree, whatever brackets are in it.
# Labelled bracketing is how constituent structure is shown inside an
# ordinary example, and it is not distinguishable from tree notation by
# looking at it — which is why the command, not the text, decides.
NOT_TREES = {
    "labelled_bracketing": ["[TP [DP John] [VP left]]"],
    "labelled_with_prose": ["[CP [C that] [TP she left]] is grammatical"],
    "two_constituents": ["[DP the cat] [VP sat on the mat]"],
    "partly_bracketed": ["Mary saw [DP the [AP very big] cat]"],
    "transcription": ["a. [ˈkæt]", "b. [ˈdɔɡ]"],
    "optional_element": ["a. [the] cat sat", "b. the cat sat"],
    "a_tree_typed_as_an_example": ["a. [DP [D the] [NP [N tree]]]",
                                   "b. [DP [D a] [NP [N cat]]]"],
}

# The numbered-tree command promises trees, so anything that is not one is
# an error naming the item — not a quiet fall back to text.
TREE_ITEM_REFUSE = {
    "unclosed": ["a. [DP [D the]", "b. [DP [D a] [NP [N cat]]]"],
    "not_brackets": ["a. just some words", "b. [DP [D a] [NP [N cat]]]"],
    "mixed_with_gloss": ["a. [DP [D the] [NP [N tree]]]",
                         "b. Esto es un ejemplo", "this is a example"],
}


def check_tree_items(ctx) -> int:
    "A paradigm of trees: one number, a letter each, and no guessing."
    # A tree item gets the row an unglossed item gets — one merged cell —
    # so it carries its own letter, judgment mark and translation, and the
    # paradigm still has exactly one number.  Which items are trees comes
    # from the command, never from the brackets.
    print("--- tree_items")
    bad = 0
    for name, (lines, groups, markers) in TREE_ITEM_CASES.items():
        doc = make_doc(ctx, lines)
        try:
            msg = run(ctx, "TreeSelectionQuiet")
        except Exception as exc:
            print(f"    FAIL: {name}: macro error {exc}")
            doc.dispose()
            bad += 1
            continue
        tables = doc.getTextTables().getCount()
        drawn = doc.getDrawPage().getCount()
        cells = []
        if tables:
            table = doc.getTextTables().getByIndex(0)
            cells = [table.getCellByName(n).getString().strip()
                     for n in table.getCellNames()
                     if table.getCellByName(n).getString().strip()]
        doc.dispose()
        found = len([c for c in cells if MARKER.match(c)])
        numbers = len([c for c in cells if c.startswith("(") and c.endswith(")")])
        if msg:
            print(f"    FAIL: {name}: macro said {msg!r}")
            bad += 1
        elif tables != 1 or drawn != groups:
            print(f"    FAIL: {name}: {tables} table(s), {drawn} tree(s), "
                  f"expected 1 and {groups}")
            bad += 1
        elif found != markers:
            print(f"    FAIL: {name}: {found} marker(s), expected {markers}")
            bad += 1
        elif numbers != 1:
            print(f"    FAIL: {name}: {numbers} numbers, a paradigm has one")
            bad += 1
        else:
            print(f"    ok — {name}: {groups} tree(s), {markers} marker(s), "
                  "one number")

    for name, lines in NOT_TREES.items():
        doc = make_doc(ctx, lines)
        msg = run(ctx)                        # Typeset example
        drawn = doc.getDrawPage().getCount()
        doc.dispose()
        if msg or drawn:
            print(f"    FAIL: {name}: Typeset example drew {drawn} tree(s), "
                  f"said {msg!r}")
            bad += 1
        else:
            print(f"    ok — {name}: left as text")

    for name, lines in TREE_ITEM_REFUSE.items():
        doc = make_doc(ctx, lines)
        msg = run(ctx, "TreeSelectionQuiet")
        made = doc.getTextTables().getCount() + doc.getDrawPage().getCount()
        doc.dispose()
        if not msg or made:
            print(f"    FAIL: {name}: built {made} where there is no tree "
                  f"to draw, said {msg!r}")
            bad += 1
        else:
            print(f"    ok — {name}: refused, {msg.splitlines()[0][:44]!r}")
    return bad


# --- an example that already has a number ------------------------------
#
# Cross-references bind to the ref-name of the NumEx field, not to the
# number it shows, so an example rebuilt with a *new* field takes every
# reference to it down with it.  These documents are written as flat ODF
# rather than assembled over UNO because the references then are the ones
# a real document has — a GetReference built over the bridge resolves
# against nothing until the file has been through the ODF import.

FODT = """<?xml version="1.0" encoding="UTF-8"?>
<office:document xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
 xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
 xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
 office:version="1.3"
 office:mimetype="application/vnd.oasis.opendocument.text">
 <office:body><office:text>
  <text:sequence-decls>
   <text:sequence-decl text:display-outline-level="0" text:name="NumEx"/>
  </text:sequence-decls>
%s
 </office:text></office:body>
</office:document>
"""


def numex(ref: str, shown: int) -> str:
    "An example number, as linguexx2odt writes one."
    # The number is written out as well as computed, exactly as the
    # converter does it: a field nothing has touched still displays, so a
    # stale example elsewhere in the fixture cannot be mistaken for the
    # rebuilt one having gone wrong.
    return (f'<text:sequence text:ref-name="{ref}" text:name="NumEx"'
            ' text:formula="ooow:NumEx+1" style:num-format="1">'
            f'{shown}</text:sequence>')


def numref(ref: str, shown: int) -> str:
    "A cross-reference to one — what a \\ref becomes."
    # A reference whose target is gone renders "Error: Reference source not
    # found" over the top of this, which is what the check is looking for.
    return ('<text:sequence-ref text:reference-format="value"'
            f' text:ref-name="{ref}">{shown}</text:sequence-ref>')


def load_doc(ctx, path: Path, paras: list[str]):
    "A document written as flat ODF, loaded the way the user's would be."
    path.write_text(FODT % "\n".join(f"  <text:p>{p}</text:p>" for p in paras),
                    encoding="utf-8")
    desktop = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.frame.Desktop", ctx)
    return desktop.loadComponentFromURL(path.as_uri(), "_blank", 0, ())


def select_paras(doc, lo: int, hi: int) -> None:
    paras = [p for p in paragraphs(doc)
             if p.supportsService("com.sun.star.text.Paragraph")]
    vc = doc.getCurrentController().getViewCursor()
    vc.gotoRange(paras[lo].getStart(), False)
    vc.gotoRange(paras[hi].getEnd(), True)


def numex_ids(doc) -> list:
    "The identity of every example number in the document."
    # SequenceValue is the ref-name every cross-reference points at.  It is
    # the whole of what has to survive a rebuild, so it is what the test
    # asks about — not the number the field happens to display, which is
    # stale until the document is laid out.
    out, it = [], doc.getTextFields().createEnumeration()
    while it.hasMoreElements():
        fld = it.nextElement()
        if not fld.supportsService("com.sun.star.text.TextField.SetExpression"):
            continue
        try:
            if fld.TextFieldMaster.Name == "NumEx":
                out.append(fld.SequenceValue)
        except Exception:                 # not a dependent field after all
            pass
    return sorted(out)


# An example carrying a number, a second example, and a paragraph
# referring to both.  Paragraphs 0-2 are the first example.
REFERENCED = [
    f"({numex('refNumEx0', 1)})\tEsto es un ejemplo glosado",
    "this is a example glossed",
    "'This is a glossed example.'",
    f"({numex('refNumEx1', 2)})\tOtro ejemplo.",
    f"See ({numref('refNumEx0', 1)}) and ({numref('refNumEx1', 2)}).",
]


def check_number_adoption(ctx, out: Path, profile: Path) -> int:
    """A number in the selection is taken over, not remade.

    The point of the rule: an example can be rebuilt — retypeset, turned
    into a tree, re-banded — without breaking a single cross-reference to
    it.  Both halves are pinned, because either alone can pass while the
    document is broken: the field's identity must be the old one
    (structure), and the reference must still render as the example's
    number rather than "Error: Reference source not found" (behaviour).
    """
    print("--- number_adoption")
    bad = 0

    doc = load_doc(ctx, out / "adopt.fodt", REFERENCED)
    before = numex_ids(doc)
    select_paras(doc, 0, 2)
    msg = run(ctx)
    after = numex_ids(doc)
    tables = doc.getTextTables().getCount()
    odt = out / "adopt.odt"
    doc.storeToURL(odt.as_uri(), (PropertyValue("FilterName", 0, "writer8", 0),))
    doc.dispose()
    text = " ".join(t for t, _x, _y in words_of(render(profile, odt)))

    if msg:
        print(f"    FAIL: macro said {msg!r}")
        bad += 1
    elif tables != 1:
        print(f"    FAIL: built {tables} table(s)")
        bad += 1
    elif after != before:
        print(f"    FAIL: the number's identity changed: {before} -> {after}")
        bad += 1
    elif "See (1) and (2)." not in " ".join(text.split()):
        print(f"    FAIL: the references did not survive: {text[:120]!r}")
        bad += 1
    elif not " ".join(text.split()).startswith("(1) Esto es un ejemplo"):
        # The parentheses the old number sat in are the macro's own, and
        # are written again with the new field.  Left in the text they
        # would come out as the first word of the example: "() Esto".
        print(f"    FAIL: the example does not begin cleanly: {text[:120]!r}")
        bad += 1
    else:
        print(f"    ok — rebuilt as (1), identities {after}, references intact")

    # The same rule under the numbered-tree command, which shares the path.
    doc = load_doc(ctx, out / "adopt_tree.fodt",
                   [f"({numex('refNumEx0', 1)})\t[DP [D the] [NP [N tree]]]",
                    f"See ({numref('refNumEx0', 1)})."])
    select_paras(doc, 0, 0)
    msg = run(ctx, "TreeSelectionQuiet")
    after = numex_ids(doc)
    drawn = doc.getDrawPage().getCount()
    doc.dispose()
    if msg or drawn != 1 or after != [0]:
        print(f"    FAIL: numbered tree: {drawn} tree(s), identities {after}, "
              f"said {msg!r}")
        bad += 1
    else:
        print("    ok — a numbered tree takes the number over too")

    # And what it refuses.  Each must leave the document as it found it:
    # a refusal that has already destroyed the field is no refusal.
    refuse = {
        "two_numbers": (REFERENCED, (0, 3), "GlossSelectionQuiet"),
        "number_part_way": ([
            "Esto es un ejemplo glosado",
            f"({numex('refNumEx0', 1)})\tthis is a example glossed",
        ], (0, 1), "GlossSelectionQuiet"),
        "bare_tree": ([
            f"({numex('refNumEx0', 1)})\t[DP [D the] [NP [N tree]]]",
        ], (0, 0), "TreeSelectionBareQuiet"),
    }
    for name, (paras, (lo, hi), macro) in refuse.items():
        doc = load_doc(ctx, out / f"adopt_{name}.fodt", paras)
        before = numex_ids(doc)
        select_paras(doc, lo, hi)
        msg = run(ctx, macro)
        made = doc.getTextTables().getCount() + doc.getDrawPage().getCount()
        after = numex_ids(doc)
        doc.dispose()
        if not msg or made or after != before:
            print(f"    FAIL: {name}: built {made}, identities {before} -> "
                  f"{after}, said {msg!r}")
            bad += 1
        else:
            print(f"    ok — {name}: refused, {msg.splitlines()[0][:44]!r}")
    return bad


# --- untypeset: the example back as the lines it was built from --------
#
# (lines in, lines out).  Out is what the example has to come back as,
# leading number aside — the same text, the braces that made a column,
# the letter and the judgment mark back at the head of their item.
UNTYPESET_CASES = {
    "plain": ([
        "Esto es un ejemplo glosado",
        "this is a example glossed",
        "'This is a glossed example.'",
    ], None),
    "judged": ([
        "*Das kleine Kind schlafen",
        "the little child sleep.INF",
        "'The little child sleeps.'",
    ], None),
    "braces": ([
        "Ich {habe geschlafen}",
        "I {have slept}",
        "'I slept.'",
    ], None),
    "unglossed": (["A simple example."], None),
    "unglossed_translated": ([
        "Ein einfaches Beispiel.",
        "'A simple example.'",
    ], None),
    "sub_examples": ([
        "a. Esto es un ejemplo",
        "this is a example",
        "'This is an example.'",
        "b. Otro ejemplo aqui",
        "another example here",
        "'Another example here.'",
    ], None),
    "sub_judged": ([
        "a. *Das kleine Kind schlafen",
        "the little child sleep.INF",
        "b. Das kleine Kind schlaeft",
        "the little child sleeps",
    ], None),
    # The one that needs the band mark: without it every band comes back
    # as another gloss tier, and this example returns six lines instead of
    # three.
    "banded": ([
        "Este es un ejemplo mucho mas largo que no cabe en una sola linea "
        "de texto de esta pagina y por eso se parte en bandas",
        "this is a example much more long that not fits in a single line "
        "of text of this page and for that reason it splits in bands",
        "'A long one.'",
    ], None),
}


def body_lines(doc) -> list[str]:
    "The document's paragraphs, as a reader sees them."
    return [p.getString() for p in paragraphs(doc)
            if p.supportsService("com.sun.star.text.Paragraph")]


NUMBER_AT_FRONT = re.compile(r"^\(\d+\)\s*")


def check_wide_example(ctx) -> int:
    "An example wider than 26 columns builds at all."
    # Writer names the 27th column "a" and not "AA" — A..Z, then lowercase,
    # then AA.  The macro generated base-26 names, so the first cell past Z
    # named no cell and the whole build died on it with "Object variable
    # not set", leaving half a table behind.  One column per word means 26
    # words, which is a long example but not a strange one.
    # Not simply "an example of 30 words": that bands, and a band is only
    # as wide as the line.  What goes past Z is the *union* of the bands'
    # boundaries, which is wider than any one of them — so the case that
    # gets there is a long example whose two tiers break in different
    # places, which is to say an ordinary long glossed example.
    print("--- wide_example")
    doc = make_doc(ctx, UNTYPESET_CASES["banded"][0])
    msg = run(ctx)
    cols = 0
    if doc.getTextTables().getCount():
        cols = doc.getTextTables().getByIndex(0).getColumns().getCount()
    doc.dispose()
    if msg or cols <= 26:
        print(f"    FAIL: said {msg!r}, built a table of {cols} columns")
        return 1
    print(f"    ok — {cols} columns, built and named right past Z")
    return 0


def check_untypeset(ctx, out: Path, profile: Path) -> int:
    """An example comes back as the lines it was built from.

    Both directions matter and are checked together, because the pair is
    the feature: text that comes back but cannot be typeset again is no
    use, and a round trip that quietly renumbers the example breaks every
    reference to it — which is the thing this whole path exists to stop.
    """
    print("--- untypeset")
    bad = 0

    for name, (lines, expected) in UNTYPESET_CASES.items():
        doc = make_doc(ctx, lines)
        msg = run(ctx)
        if msg:
            print(f"    FAIL: {name}: typesetting said {msg!r}")
            doc.dispose()
            bad += 1
            continue
        before = numex_ids(doc)
        table = doc.getTextTables().getByIndex(0)
        vc = doc.getCurrentController().getViewCursor()
        vc.gotoRange(table.getCellByName("A2").getText().getStart(), False)
        msg = run(ctx, "UntypesetSelectionQuiet")
        got = [ln for ln in body_lines(doc) if ln.strip()]
        after = numex_ids(doc)
        tables = doc.getTextTables().getCount()

        # and back again: the same example, keeping its number
        again = ""
        if not msg and got:
            select_paras(doc, 0, len(got) - 1)
            again = run(ctx)
        rebuilt = numex_ids(doc)
        n_tables = doc.getTextTables().getCount()
        doc.dispose()

        want = expected if expected is not None else lines
        got = [NUMBER_AT_FRONT.sub("", ln).strip() for ln in got]
        if msg:
            print(f"    FAIL: {name}: {msg!r}")
            bad += 1
        elif tables:
            print(f"    FAIL: {name}: the table is still there")
            bad += 1
        elif got != [ln.strip() for ln in want]:
            print(f"    FAIL: {name}: came back as {got}, wanted {want}")
            bad += 1
        elif after != before:
            print(f"    FAIL: {name}: the number changed: {before} -> {after}")
            bad += 1
        elif again or n_tables != 1 or rebuilt != before:
            print(f"    FAIL: {name}: rebuilding said {again!r}, "
                  f"{n_tables} table(s), numbers {rebuilt}")
            bad += 1
        else:
            print(f"    ok — {name}: {len(got)} line(s) back, number kept")

    bad += check_untypeset_references(ctx, out, profile)
    bad += check_untypeset_adjacent(ctx)
    bad += check_untypeset_converted(ctx, out)
    bad += check_untypeset_annot(ctx, out)
    bad += check_untypeset_trees(ctx)
    bad += check_untypeset_formatting(ctx)
    bad += check_untypeset_refusals(ctx)
    return bad


def check_untypeset_references(ctx, out: Path, profile: Path) -> int:
    """The whole point, end to end: an example is changed and the
    cross-references to it still resolve."""
    doc = load_doc(ctx, out / "roundtrip.fodt", REFERENCED)
    select_paras(doc, 0, 2)
    msgs = [run(ctx)]                       # typeset, taking the number over
    table = doc.getTextTables().getByIndex(0)
    vc = doc.getCurrentController().getViewCursor()
    vc.gotoRange(table.getCellByName("A2").getText().getStart(), False)
    msgs.append(run(ctx, "UntypesetSelectionQuiet"))

    # the linguist changes the example: a new object line, a new gloss
    paras = [p for p in paragraphs(doc)
             if p.supportsService("com.sun.star.text.Paragraph")]
    paras[0].getEnd().setString(" completamente distinto")
    select_paras(doc, 0, 2)
    msgs.append(run(ctx))                   # and typeset it again

    ids = numex_ids(doc)
    odt = out / "roundtrip.odt"
    doc.storeToURL(odt.as_uri(), (PropertyValue("FilterName", 0, "writer8", 0),))
    doc.dispose()
    text = " ".join(" ".join(t for t, _x, _y in words_of(render(profile, odt))).split())

    if any(msgs):
        print(f"    FAIL: references: the macro said {msgs!r}")
        return 1
    if ids != [0, 1]:
        print(f"    FAIL: references: the numbers came out {ids}, wanted [0, 1]")
        return 1
    if "See (1) and (2)." not in text:
        print(f"    FAIL: references: did not survive the round trip: "
              f"{text[:140]!r}")
        return 1
    if "completamente distinto" not in text:
        print("    FAIL: references: the edit is not in the rebuilt example")
        return 1
    print("    ok — changed an example and its references still resolve")
    return 0


def check_untypeset_adjacent(ctx) -> int:
    """An example with another example butted straight up against it.

    Two examples in a row have no paragraph between them — the converter
    emits exactly this, and so does anyone who typesets two examples one
    after the other — so there is nowhere to write the text back to until
    Writer is asked to make room.  The first attempt at this refused the
    commonest arrangement in a linguistics paper.
    """
    doc = make_doc(ctx, ["Primero ejemplo aqui", "first example here",
                         "Segundo ejemplo aqui", "second example here"])
    msgs = []
    for lo, hi in ((2, 3), (0, 1)):        # bottom one first
        select_paras(doc, lo, hi)
        msgs.append(run(ctx))
    tables = doc.getTextTables().getCount()

    # untypeset the *first* of the two, which is followed by a table.
    # In document order: getTextTables() is in the order they were built,
    # and the bottom one was built first.
    if tables == 2:
        table = [el for el in paragraphs(doc)
                 if el.supportsService("com.sun.star.text.TextTable")][0]
        vc = doc.getCurrentController().getViewCursor()
        vc.gotoRange(table.getCellByName("A2").getText().getStart(), False)
        msgs.append(run(ctx, "UntypesetSelectionQuiet"))
    lines = [ln for ln in body_lines(doc) if ln.strip()]
    left = doc.getTextTables().getCount()
    doc.dispose()

    if any(msgs):
        print(f"    FAIL: adjacent: the macro said {msgs!r}")
        return 1
    if tables != 2 or left != 1:
        print(f"    FAIL: adjacent: built {tables} table(s), {left} left")
        return 1
    got = [NUMBER_AT_FRONT.sub("", ln).strip() for ln in lines]
    if got != ["Primero ejemplo aqui", "first example here"]:
        print(f"    FAIL: adjacent: came back as {got}")
        return 1
    print("    ok — an example with another one right after it")
    return 0


CONVERTED = r"""\begin{document}
Some prose before it.

\ex. \gll Esto es un ejemplo glosado que resulta bastante largo para llenar toda la linea entera del bloque de texto \\
     this is a example glossed that turns.out rather long to fill all the line whole of.the block of text \\
\glt `A long converted example.'

\ex. \gll Ich habe geschlafen \\
     I have slept \\
\glt `I slept.'

Prose after it.
\end{document}"""


def check_untypeset_converted(ctx, out: Path) -> int:
    """A document the *converter* made, taken apart by the macro.

    The two build their tables by different routes — one writes ODF, the
    other drives Writer — so reading one with the other is the claim that
    they are the same object, and this is where it is tested rather than
    asserted.  The example chosen is a banded one, because the band mark
    is the only thing in the table that had to be agreed between them.
    """
    tex = out / "converted.tex"
    tex.write_text(CONVERTED, encoding="utf-8")
    odt = out / "converted.odt"
    built = subprocess.run(
        [sys.executable, "-m", "linguexx2odt.cli", str(tex), "-o", str(odt)],
        capture_output=True, text=True, timeout=300,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    if built.returncode or not odt.is_file():
        # pandoc is the converter's own dependency, not this harness's
        print(f"    skipped — the converter did not run: "
              f"{(built.stdout + built.stderr).strip()[:80]!r}")
        return 0

    desktop = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.frame.Desktop", ctx)
    doc = desktop.loadComponentFromURL(odt.as_uri(), "_blank", 0, ())
    before = numex_ids(doc)
    table = [el for el in paragraphs(doc)
             if el.supportsService("com.sun.star.text.TextTable")][0]
    vc = doc.getCurrentController().getViewCursor()
    vc.gotoRange(table.getCellByName("A2").getText().getStart(), False)
    msg = run(ctx, "UntypesetSelectionQuiet")
    lines = [ln for ln in body_lines(doc) if ln.strip()]

    again = ""
    if not msg and len(lines) >= 4:
        select_paras(doc, 1, 3)                  # the example, not the prose
        again = run(ctx)
    after = numex_ids(doc)
    tables = doc.getTextTables().getCount()
    doc.dispose()

    if msg:
        print(f"    FAIL: converted: {msg!r}")
        return 1
    # three lines back, not six: the converter marks its continuation
    # bands and the macro reads the marks
    got = [NUMBER_AT_FRONT.sub("", ln).strip() for ln in lines]
    if len(got) != 5 or not got[1].startswith("Esto es un ejemplo"):
        print(f"    FAIL: converted: came back as {got}")
        return 1
    if again or tables != 2 or after != before:
        print(f"    FAIL: converted: rebuilding said {again!r}, {tables} "
              f"table(s), numbers {before} -> {after}")
        return 1
    print("    ok — a converted document untypesets and rebuilds, bands and all")
    return 0


ANNOTATED = r"""\begin{document}
\ex. \gll que Pierre est fatigu\'e \exannot{[CP]}\\
     that Pierre is tired\\
\glt `that Pierre is tired'
\end{document}
"""


def check_untypeset_annot(ctx, out: Path) -> int:
    r"""An \exannot label survives the trip out of the converter and back.

    It did not, and the failure was quiet.  The macro read the annotation
    column as one more cell of the object tier, so a converted

        \gll que Pierre est fatigué \exannot{[CP]}

    came back as "que Pierre est fatigué [CP]" -- the wrapper gone and the
    label now a fifth object word -- and re-typesetting that built an
    eight-column grid where the original is seven, with the gloss no longer
    under its word.

    Both halves are checked, because either alone can pass for the wrong
    reason: the text must come back as \exannot{...}, and re-typesetting it
    must put the label in a column of its own at ANNOT_RATIO of the table,
    not in a word cell.
    """
    tex = out / "annotated.tex"
    tex.write_text(ANNOTATED, encoding="utf-8")
    odt = out / "annotated.odt"
    built = subprocess.run(
        [sys.executable, "-m", "linguexx2odt.cli", str(tex), "-o", str(odt)],
        capture_output=True, text=True, timeout=300,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    if built.returncode or not odt.is_file():
        print(f"    skipped — the converter did not run: "
              f"{(built.stdout + built.stderr).strip()[:80]!r}")
        return 0

    desktop = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.frame.Desktop", ctx)
    doc = desktop.loadComponentFromURL(odt.as_uri(), "_blank", 0, ())
    table = [el for el in paragraphs(doc)
             if el.supportsService("com.sun.star.text.TextTable")][0]
    vc = doc.getCurrentController().getViewCursor()
    vc.gotoRange(table.getCellByName("A2").getText().getStart(), False)
    msg = run(ctx, "UntypesetSelectionQuiet")
    lines = [ln for ln in body_lines(doc) if ln.strip()]
    doc.dispose()

    if msg:
        print(f"    FAIL: annotated: {msg!r}")
        return 1
    object_line = NUMBER_AT_FRONT.sub("", lines[0]).strip() if lines else ""
    if "\\exannot{[CP]}" not in object_line:
        print(f"    FAIL: annotated: came back as {object_line!r}, "
              f"without its \\exannot wrapper")
        return 1

    # ... and it rebuilds into a column rather than a word
    doc2 = make_doc(ctx, [NUMBER_AT_FRONT.sub("", ln).strip() for ln in lines])
    again = run(ctx)
    t2 = doc2.getTextTables().getByIndex(0)
    seps = [s.Position for s in t2.TableColumnSeparators]
    labelled = [n for n in t2.getCellNames()
                if t2.getCellByName(n).getString().strip() == "[CP]"]
    doc2.dispose()
    if again:
        print(f"    FAIL: annotated: rebuilding said {again!r}")
        return 1
    if len(labelled) != 1:
        print(f"    FAIL: annotated: the label is in {len(labelled)} cell(s)")
        return 1
    at = seps[-1] / 100 if seps else 0
    if abs(at - 75.0) > 0.5:
        print(f"    FAIL: annotated: label column at {at:.2f}%, not 75%")
        return 1
    print("    ok — an \\exannot label survives the converter round trip, "
          "and rebuilds into its own column")
    return 0


# A tree comes back as the brackets it was drawn from, which the drawing
# carries.  (lines in, lines out, trees drawn)
UNTYPESET_TREES = {
    "one_tree": (["[DP [D the] [NP [N tree]]]"], None, 1),
    "judged": (["*[S [NP him] [VP [V left]]]"], None, 1),
    "with_movement": ([
        "[CP [DP,name=w what] [TP [V saw] [DP,name=t __]]]",
        "move t -> w",
    ], None, 1),
    "paradigm": ([
        "a. [DP [D the] [NP [N tree]]]",
        "b. [DP [D a] [NP [N cat]]]",
    ], None, 2),
    "paradigm_judged_with_move": ([
        "a. *[CP [DP,name=w what] [TP [V saw] [DP,name=t __]]]",
        "move t -> w",
        "b. [DP [D a] [NP [N cat]]]",
    ], None, 2),
    "with_translation": ([
        "[DP [D the] [NP [N tree]]]",
        "'the tree'",
    ], None, 1),
}


def check_untypeset_trees(ctx) -> int:
    """A drawn tree comes back as its brackets, and draws again.

    The drawing cannot be read back — shapes have positions, not
    structure — so the tree carries its own source, and this is the pin on
    that: what comes out has to be what went in, letters and move lines
    included, and it has to draw the same tree again afterwards.
    """
    bad = 0
    for name, (lines, expected, trees) in UNTYPESET_TREES.items():
        doc = make_doc(ctx, lines)
        msg = run(ctx, "TreeSelectionQuiet")
        before = numex_ids(doc)
        if not msg:
            table = doc.getTextTables().getByIndex(0)
            vc = doc.getCurrentController().getViewCursor()
            vc.gotoRange(table.getCellByName("A2").getText().getStart(), False)
            msg = run(ctx, "UntypesetSelectionQuiet")
        got = [ln for ln in body_lines(doc) if ln.strip()]
        drawn = doc.getDrawPage().getCount()

        again = ""
        if not msg and got:
            select_paras(doc, 0, len(got) - 1)
            again = run(ctx, "TreeSelectionQuiet")
        rebuilt = numex_ids(doc)
        redrawn = doc.getDrawPage().getCount()
        tables = doc.getTextTables().getCount()
        doc.dispose()

        want = [ln.strip() for ln in (expected if expected is not None else lines)]
        got = [NUMBER_AT_FRONT.sub("", ln).strip() for ln in got]
        if msg:
            print(f"    FAIL: tree {name}: {msg!r}")
            bad += 1
        elif drawn:
            print(f"    FAIL: tree {name}: {drawn} drawing(s) left behind")
            bad += 1
        elif got != want:
            print(f"    FAIL: tree {name}: came back as {got}, wanted {want}")
            bad += 1
        elif again or redrawn != trees or tables != 1 or rebuilt != before:
            print(f"    FAIL: tree {name}: redrawing said {again!r}, "
                  f"{redrawn} tree(s) of {trees}, {tables} table(s), "
                  f"numbers {before} -> {rebuilt}")
            bad += 1
        else:
            print(f"    ok — tree {name}: {len(got)} line(s) back, "
                  f"{redrawn} redrawn, number kept")
    return bad


def check_untypeset_formatting(ctx) -> int:
    "Small caps went into the table and small caps come back out of it."
    # The gloss tier is the one linguists format, and it is the one a
    # careless round trip flattens: the text would look right and the
    # LxLeipzig-style small caps would be gone.
    doc = make_doc(ctx, [
        "Ich habe geschlafen",
        [("ich ", False), ("1sg", True), (" have-", False), ("prf", True)],
        "'I slept.'",
    ])
    msg = run(ctx)
    table = doc.getTextTables().getByIndex(0)
    vc = doc.getCurrentController().getViewCursor()
    vc.gotoRange(table.getCellByName("A2").getText().getStart(), False)
    msg = msg or run(ctx, "UntypesetSelectionQuiet")

    small: list[str] = []
    for par in paragraphs(doc):
        if not par.supportsService("com.sun.star.text.Paragraph"):
            continue
        it = par.createEnumeration()
        while it.hasMoreElements():
            por = it.nextElement()
            if por.CharCaseMap == SMALLCAPS and por.getString().strip():
                small.append(por.getString().strip())
    doc.dispose()

    if msg:
        print(f"    FAIL: formatting: {msg!r}")
        return 1
    if small != ["1sg", "prf"]:
        print(f"    FAIL: formatting: small caps came back as {small}")
        return 1
    print("    ok — formatting survives the round trip")
    return 0


def check_untypeset_refusals(ctx) -> int:
    """What it will not take apart.  Each must leave the document alone:
    this command deletes a table, so a wrong yes is unrecoverable."""
    bad = 0

    # not in a table at all
    doc = make_doc(ctx, ["Esto es un ejemplo", "this is a example"])
    msg = run(ctx, "UntypesetSelectionQuiet")
    lines = len([ln for ln in body_lines(doc) if ln.strip()])
    doc.dispose()
    if not msg or lines != 2:
        print(f"    FAIL: outside a table: said {msg!r}, {lines} line(s) left")
        bad += 1
    else:
        print(f"    ok — outside a table: refused, {msg.splitlines()[0][:40]!r}")

    # the linguist's own table
    doc = make_doc(ctx, ["Something."])
    text = doc.getText()
    table = doc.createInstance("com.sun.star.text.TextTable")
    table.initialize(2, 2)
    text.insertTextContent(text.getEnd(), table, False)
    table.getCellByName("A1").setString("data")
    vc = doc.getCurrentController().getViewCursor()
    vc.gotoRange(table.getCellByName("A1").getText().getStart(), False)
    msg = run(ctx, "UntypesetSelectionQuiet")
    kept = doc.getTextTables().getCount()
    doc.dispose()
    if not msg or kept != 1:
        print(f"    FAIL: a plain table: said {msg!r}, {kept} table(s) left")
        bad += 1
    else:
        print(f"    ok — a plain table: refused, {msg.splitlines()[0][:40]!r}")

    # a drawing that is not one of ours: a tree carries the brackets it was
    # drawn from, and anything that carries none cannot be given back
    doc = make_doc(ctx, ["[DP [D the] [NP [N tree]]]"])
    msg = run(ctx, "TreeSelectionQuiet")
    doc.getDrawPage().getByIndex(0).Title = "holiday photo"   # not ours now
    table = doc.getTextTables().getByIndex(0)
    vc = doc.getCurrentController().getViewCursor()
    vc.gotoRange(table.getCellByName("A2").getText().getStart(), False)
    msg = run(ctx, "UntypesetSelectionQuiet")
    kept = doc.getTextTables().getCount() + doc.getDrawPage().getCount()
    doc.dispose()
    if not msg or kept != 2:
        print(f"    FAIL: a foreign drawing: said {msg!r}, {kept} left of 2")
        bad += 1
    else:
        print(f"    ok — a foreign drawing: refused, {msg.splitlines()[0][:40]!r}")
    return bad


def check_undo(ctx) -> int:
    "One Ctrl+Z takes the whole thing back, whatever was built."
    # Promised in the docs and pinned by nothing until now.  The specific
    # regression: creating the example styles *outside* the undo context
    # leaves one entry per style on the stack, so the first tree in a
    # document unwinds a step at a time — the thing the context is for.
    print("--- undo")
    bad = 0
    for what, macro, lines in (
            ("example", "GlossSelectionQuiet",
             ["Esto es un ejemplo", "this is a example", "'An example.'"]),
            ("tree", "TreeSelectionQuiet", ["[DP [D the] [NP [N tree]]]"]),
            ("tree with movement", "TreeSelectionQuiet",
             ["[CP [DP,name=w what] [TP [V saw] [DP,name=t __]]]",
              "move t -> w"]),
            ("bare tree", "TreeSelectionBareQuiet",
             ["[DP [D the] [NP [N tree]]]"])):
        doc = make_doc(ctx, lines)
        before = doc.getText().getString().strip()
        msg = run(ctx, macro)
        made = doc.getTextTables().getCount() + doc.getDrawPage().getCount()
        manager = doc.getUndoManager()
        stack = list(manager.getAllUndoActionTitles())
        manager.undo()                            # exactly one Ctrl+Z
        left = doc.getTextTables().getCount() + doc.getDrawPage().getCount()
        after = doc.getText().getString().strip()
        doc.dispose()

        if msg or not made:
            print(f"    FAIL: {what}: said {msg!r}, built {made}")
            bad += 1
        elif left:
            print(f"    FAIL: {what}: {left} thing(s) survived one undo")
            bad += 1
        elif after != before:
            print(f"    FAIL: {what}: the text came back as {after[:40]!r}")
            bad += 1
        elif any(t.startswith("Create paragraph style") for t in stack):
            loose = [t for t in stack if t.startswith("Create paragraph style")]
            print(f"    FAIL: {what}: {len(loose)} style(s) left their own "
                  "undo entries outside the context")
            bad += 1
    if not bad:
        print("    ok — example, tree, tree with movement and bare tree "
              "each come back in one step")

    # Untypeset undoes in one step too, and it has more moving parts than
    # any of the above: it asks Writer for a paragraph, writes the lines
    # and takes the table away, and all three are one Ctrl+Z.
    doc = make_doc(ctx, ["Esto es un ejemplo", "this is a example"])
    msg = run(ctx)
    built = doc.getText().getString().strip()
    table = doc.getTextTables().getByIndex(0)
    vc = doc.getCurrentController().getViewCursor()
    vc.gotoRange(table.getCellByName("A2").getText().getStart(), False)
    msg = msg or run(ctx, "UntypesetSelectionQuiet")
    doc.getUndoManager().undo()
    tables = doc.getTextTables().getCount()
    after = doc.getText().getString().strip()
    doc.dispose()
    if msg:
        print(f"    FAIL: untypeset: {msg!r}")
        bad += 1
    elif tables != 1 or after != built:
        print(f"    FAIL: untypeset: one undo left {tables} table(s) and "
              f"{after[:40]!r}")
        bad += 1
    else:
        print("    ok — untypeset comes back in one step as well")
    return bad


def check_extension(out: Path) -> int:
    "The packaged extension, installed and driven — not the loose .bas."
    # The rest of the suite puts LinguExx.bas straight into a profile's
    # Basic library, which skips the package entirely.  That has hidden a
    # real bug before: a missing dialog.xlb made every desktop start
    # complain while the headless tests stayed green (see notes/findings).
    print("--- extension")
    oxt = out / "linguexx.oxt"
    built = subprocess.run(
        [sys.executable, str(HERE / "build_oxt.py"), "-o", str(oxt)],
        capture_output=True, text=True, timeout=120)
    if built.returncode or not oxt.is_file():
        print(f"    FAIL: build_oxt.py: {(built.stdout + built.stderr)[:200]}")
        return 1

    # Every command the menu offers must name a Sub that exists.  The menu
    # invokes the interactive entry points, which nothing else here calls,
    # so a typo in Addons.xcu would otherwise ship unnoticed.
    bad = 0
    with zipfile.ZipFile(oxt) as zf:
        members = set(zf.namelist())
        xcu = zf.read("Addons.xcu").decode()
    for needed in ("Addons.xcu", "LinguExx/Gloss.xba", "LinguExx/script.xlb",
                   "LinguExx/dialog.xlb", "description.xml",
                   "META-INF/manifest.xml"):
        if needed not in members:
            print(f"    FAIL: the package has no {needed}")
            bad += 1
    source = writermacro.source()
    commands = re.findall(r"script:LinguExx\.Gloss\.(\w+)\?", xcu)
    if not commands:
        print("    FAIL: Addons.xcu offers no commands")
        bad += 1
    for name in commands:
        if f"Sub {name}" not in source:
            print(f"    FAIL: the menu runs {name}, which the macro "
                  "does not define")
            bad += 1
    if bad:
        return bad

    profile = out / "oxt-profile"
    added = subprocess.run(
        ["unopkg", "add", "-f", f"-env:UserInstallation=file://{profile}",
         str(oxt)], capture_output=True, text=True, timeout=300)
    if added.returncode:
        print(f"    FAIL: unopkg add: {(added.stdout + added.stderr)[:200]}")
        return 1

    # note: no install() — whatever runs now came out of the package
    ctx = connect(profile)
    for macro, lines in (("GlossSelectionQuiet",
                          ["Esto es un ejemplo", "this is a example"]),
                         ("TreeSelectionQuiet", ["[DP [D the] [NP [N tree]]]"]),
                         ("TreeSelectionBareQuiet",
                          ["[DP [D the] [NP [N tree]]]"])):
        doc = make_doc(ctx, lines)
        try:
            msg = run(ctx, macro)
            made = doc.getTextTables().getCount() + doc.getDrawPage().getCount()
        except Exception as exc:
            print(f"    FAIL: {macro} is not in the installed extension: {exc}")
            doc.dispose()
            bad += 1
            continue
        doc.dispose()
        if msg or not made:
            print(f"    FAIL: {macro} through the extension: {msg!r}, "
                  f"built {made}")
            bad += 1
    if not bad:
        print(f"    ok — packaged, installed, and all {len(commands)} menu "
              "commands run from it")
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
    failures += check_items_keep_their_own_columns(ctx, out, profile)
    failures += check_layout_settings(ctx, out, profile)
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
    failures += check_small_caps(ctx, out, profile)
    failures += check_formatting_round_trip(ctx)
    failures += check_trees(ctx)
    failures += check_tree_geometry(ctx)
    failures += check_bare_tree(ctx, out, profile)
    failures += check_moves(ctx)
    failures += check_move_geometry(ctx)
    failures += check_arrow_clearance(ctx)
    failures += check_tree_alignment(ctx, out, profile)
    failures += check_tree_formatting(ctx)

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
    failures += check_autocorrect_spaces(ctx)
    failures += check_tree_items(ctx)
    failures += check_number_adoption(ctx, out, profile)
    failures += check_wide_example(ctx)
    failures += check_untypeset(ctx, out, profile)
    failures += check_undo(ctx)
    failures += check_extension(out)
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
    try:
        raise SystemExit(main())
    finally:
        shutdown()          # never leave a soffice holding a port
