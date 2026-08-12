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

"""What of LinguExx.bas could run in Impress?  Asked of a real Impress.

The macro stands on five things, and this reports which of them a slide
has.  See the findings entry of 2026-08-12; the short of it is that the
examples cannot be the same object there (no paragraph styles, no
sequence fields, no text tables) while the trees could be, because what
they are built from — measuring by rendering, and a group of shapes —
behaves the same.

    python3 spikes/impress_probe.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import uno  # type: ignore  # noqa: E402
from com.sun.star.awt import Point, Size  # type: ignore  # noqa: E402

from run_macro_test import connect, shutdown  # noqa: E402

SMALLCAPS = 4                                # com.sun.star.style.CaseMap
PARAGRAPH_BREAK = 0


def report(label: str, fn) -> None:
    try:
        print(f"  {label}: {fn()}")
    except Exception as exc:                 # the answer, not a crash
        print(f"  {label}: {type(exc).__name__}: {str(exc)[:70]}")


def main() -> int:
    ctx = connect(Path(tempfile.mkdtemp(prefix="impress-probe-")))
    desktop = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.frame.Desktop", ctx)
    doc = desktop.loadComponentFromURL(
        "private:factory/simpress", "_blank", 0, ())
    page = doc.getDrawPages().getByIndex(0)

    print("\n1. named paragraph styles — LxEnsureStyles, and every cell")
    print("   style families:", list(doc.getStyleFamilies().getElementNames()))
    report("a ParagraphStyle instance", lambda: doc.createInstance(
        "com.sun.star.style.ParagraphStyle") and "created")

    print("\n2. the NumEx field — the number, and every cross-reference")
    report("SetExpression master", lambda: doc.createInstance(
        "com.sun.star.text.FieldMaster.SetExpression") and "created")
    report("SetExpression field", lambda: doc.createInstance(
        "com.sun.star.text.TextField.SetExpression") and "created")
    report("getTextFieldMasters", lambda: doc.getTextFieldMasters() and "present")
    report("a presentation field (what Impress does have)",
           lambda: doc.createInstance(
               "com.sun.star.presentation.TextField.Header") and "created")

    print("\n3. the table the example is laid out in")
    report("TextTable", lambda: doc.createInstance(
        "com.sun.star.text.TextTable") and "created")

    def table_shape():
        shape = doc.createInstance("com.sun.star.drawing.TableShape")
        page.add(shape)
        shape.setPosition(Point(2000, 2000))
        shape.setSize(Size(20000, 4000))
        model = shape.Model
        model.Rows.insertByIndex(1, 2)
        model.Columns.insertByIndex(1, 4)
        cell = model.getCellByPosition(0, 0)
        cell.setString("Esto")
        try:
            cell.getText().createTextCursor().ParaStyleName = "Standard"
            styled = "ParaStyleName accepted"
        except Exception as exc:
            styled = f"ParaStyleName refused ({type(exc).__name__})"
        return (f"{model.Rows.getCount()}x{model.Columns.getCount()}, "
                f"cell {model.getCellByPosition(0, 0).getString()!r}, {styled}")

    report("drawing TableShape", table_shape)

    print("\n4. measuring by rendering — what LxTMeasure does")

    def measure():
        shape = doc.createInstance("com.sun.star.drawing.TextShape")
        page.add(shape)
        shape.setPosition(Point(0, 0))
        shape.setSize(Size(1000, 1000))
        shape.TextAutoGrowWidth = True
        shape.TextAutoGrowHeight = True
        for name in ("TextLeftDistance", "TextRightDistance",
                     "TextUpperDistance", "TextLowerDistance"):
            setattr(shape, name, 0)
        out = []
        for word in ("DP", "the tree", "a much longer label"):
            shape.setString(word)
            out.append((word, shape.getSize().Width))
        page.remove(shape)
        return out

    report("scratch TextShape widths, 1/100 mm", measure)

    print("\n5. the drawing itself — LxTreeShapes")
    report("page size, 1/100 mm", lambda: f"{page.Width}x{page.Height}")

    def group_and_anchor():
        coll = ctx.ServiceManager.createInstance(
            "com.sun.star.drawing.ShapeCollection")
        for i in range(2):
            shape = doc.createInstance("com.sun.star.drawing.TextShape")
            page.add(shape)
            shape.setPosition(Point(1000 * i, 1000))
            shape.setSize(Size(900, 500))
            shape.setString(f"n{i}")
            coll.add(shape)
        group = page.group(coll)
        try:
            group.AnchorType = uno.Enum(
                "com.sun.star.text.TextContentAnchorType", "AS_CHARACTER")
            anchored = "AnchorType accepted"
        except Exception as exc:
            anchored = f"AnchorType refused ({type(exc).__name__})"
        return f"grouped, {anchored}"

    report("group + as-character anchor", group_and_anchor)

    print("\n6. reading the selection — what LxSelectedLines walks")

    def read_selection():
        shape = doc.createInstance("com.sun.star.drawing.TextShape")
        page.add(shape)
        shape.setPosition(Point(2000, 8000))
        shape.setSize(Size(18000, 4000))
        text = shape.getText()
        cur = text.createTextCursor()
        text.insertString(cur, "[DP [D the] [NP [N ", False)
        cur.CharCaseMap = SMALLCAPS          # as a linguist marks a gloss
        text.insertString(cur, "tree", False)
        cur.CharCaseMap = 0
        text.insertString(cur, "]]]", False)
        text.insertControlCharacter(cur, PARAGRAPH_BREAK, False)
        text.insertString(cur, "move t -> w", False)

        doc.getCurrentController().select(shape)
        obj = doc.getCurrentController().getSelection().getByIndex(0)
        out = []
        pars = obj.getText().createEnumeration()
        while pars.hasMoreElements():
            pors = pars.nextElement().createEnumeration()
            while pors.hasMoreElements():
                por = pors.nextElement()
                out.append((getattr(por, "TextPortionType", "<none>"),
                            por.getString(), por.CharCaseMap))
        return out

    report("portions of a selected text shape", read_selection)
    doc.close(False)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        shutdown()
