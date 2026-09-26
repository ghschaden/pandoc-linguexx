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

"""Measure a face from its font file into measure._FACE_ADVANCE.

    python3 tools/measure_face.py Aptos.ttf            # check the committed table
    python3 tools/measure_face.py Aptos.ttf --write    # write it

The converter and both add-ins estimate column widths from per-character
advances.  Times is the built-in table; a face measured here is carried
beside it, so it is estimated from its own metrics on a machine that has
never installed it.  Only the numbers are committed, never the font.

Aptos, Word's default body face since 2023, came from Microsoft's own
download (Download Center id 106087, "Microsoft Aptos Fonts.zip", 4.40,
Aptos.ttf version 2.01) -- the face a Word user's examples are set in.

The measurement is measure.measure_font_file(), the same function the
converter uses for an installed face, so a committed table and a live
reading of the same file cannot disagree.
"""

from __future__ import annotations

import pprint
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from linguexx2odt import measure  # noqa: E402

MEASURE = ROOT / "src" / "linguexx2odt" / "measure.py"
BLOCK = re.compile(
    r"(# --- BEGIN MEASURED FACES[^\n]*\n)_FACE_ADVANCE: dict\[str, dict\[str, float\]\] = .*?\n"
    r"(# --- END MEASURED FACES)", re.S)


def family(path: str) -> str:
    from fontTools.ttLib import TTFont
    name = TTFont(path, fontNumber=0, lazy=True)["name"]
    fam = name.getDebugName(16) or name.getDebugName(1)
    return fam.lower().replace(" ", "")


def main(argv: list[str]) -> int:
    paths = [a for a in argv if not a.startswith("--")]
    if not paths:
        sys.exit(__doc__)
    faces = dict(measure._FACE_ADVANCE)
    drift = 0
    for path in paths:
        key = family(path)
        got = measure.measure_font_file(path)
        if faces.get(key) == got:
            print(f"{key}: the committed table is this font's")
        else:
            print(f"{key}: {'not committed' if key not in faces else 'differs from the font'}")
            drift += 1
        faces[key] = got
    if "--write" in argv:
        source = MEASURE.read_text(encoding="utf-8")
        body = pprint.pformat(faces, width=76, sort_dicts=False)
        new, n = BLOCK.subn(lambda m: m.group(1) + "_FACE_ADVANCE: dict[str, dict[str, float]] = "
                            + body + "\n" + m.group(2), source)
        if n != 1:
            sys.exit(f"{MEASURE}: the MEASURED FACES block was not found")
        MEASURE.write_text(new, encoding="utf-8")
        print(f"{MEASURE.name}: written")
        return 0
    return 1 if drift else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
