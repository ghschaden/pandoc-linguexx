#!/usr/bin/env python3
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

"""Check measure._ADVANCE against the font it claims to describe.

The converter has no font metrics at conversion time, so it carries a table
of them.  This is where the table came from, and how to find out that it
has drifted:

    python3 tools/measure_advances.py            # check
    python3 tools/measure_advances.py --print    # reprint the literal

Needs a running-capable LibreOffice, like tools/run_macro_test.py — the
measurement is done by asking the real font.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))

import uno  # type: ignore  # noqa: E402

import run_macro_test as harness  # noqa: E402
from linguexx2odt.measure import _ADVANCE  # noqa: E402

#: The face the estimate targets.  Liberation Serif is metric-compatible
#: with Times New Roman, so its advances are the ones to carry.
FONT = "Liberation Serif"
SIZE_PT = 200.0          # large enough that rounding is well under 0.005 em
TOLERANCE = 0.003


def measured() -> dict[str, float]:
    ctx = harness.connect(Path(tempfile.mkdtemp(prefix="lx-advances-")) / "profile")
    try:
        device = ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.awt.Toolkit", ctx).createScreenCompatibleDevice(400, 400)
        px_per_cm = device.getInfo().PixelPerMeterX / 100.0
        descriptor = uno.createUnoStruct("com.sun.star.awt.FontDescriptor")
        descriptor.Name = FONT
        descriptor.Height = round(SIZE_PT / 72.0 * 2.54 * px_per_cm)
        font = device.getFont(descriptor)
        em = SIZE_PT / 72.0 * 2.54 * px_per_cm
        # Coverage comes from the font, never from the width: the notdef box
        # is 0.78 em and so are 'm' and '&', which a width test drops.
        return {ch: round(font.getStringWidth(ch) / em, 3)
                for ch in _ADVANCE if font.hasGlyphs(ch)}
    finally:
        harness.shutdown()


def main() -> int:
    real = measured()
    if "--print" in sys.argv:
        line = "    "
        for ch, width in sorted(real.items()):
            piece = f"{ch!r}: {width},"
            if len(line) + len(piece) > 74:
                print(line.rstrip())
                line = "    "
            line += piece + " "
        print(line.rstrip())
        return 0

    absent = sorted(set(_ADVANCE) - set(real))
    wrong = [(ch, _ADVANCE[ch], real[ch]) for ch in sorted(real)
             if abs(_ADVANCE[ch] - real[ch]) > TOLERANCE]
    if absent:
        print(f"{len(absent)} character(s) in the table are not in {FONT}: "
              f"{''.join(absent)!r}")
    for ch, table, got in wrong:
        print(f"{ch!r}: table says {table}, {FONT} says {got}")
    if absent or wrong:
        print(f"\nmeasure._ADVANCE has drifted from {FONT}; "
              "reprint it with --print")
        return 1
    print(f"measure._ADVANCE: {len(real)} advances, all within "
          f"{TOLERANCE} em of {FONT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
