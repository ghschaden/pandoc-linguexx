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

"""Reading word positions out of a rendered PDF.

Shared by the converter's end-to-end tests and by the Writer macro's
harness (tools/run_macro_test.py), which measure the same thing about the
same kind of document and had drifted into two copies of this.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {"x": "http://www.w3.org/1999/xhtml"}


def words(pdf: Path) -> list[tuple[str, float, float]]:
    """(text, x, y) for every word, in reading order.

    y is offset per page so that sorting by y keeps the pages in order — a
    document that spills onto a second page must not have its assertions
    stop at the first one.
    """
    xml = subprocess.run(["pdftotext", "-bbox", str(pdf), "-"],
                         check=True, capture_output=True, text=True).stdout
    out: list[tuple[str, float, float]] = []
    for n, page in enumerate(ET.fromstring(xml).findall(".//x:page", NS)):
        offset = n * (float(page.get("height")) + 1)
        out += [(w.text, float(w.get("xMin")), float(w.get("yMin")) + offset)
                for w in page.findall(".//x:word", NS)]
    return out


def rows(pdf: Path) -> dict[int, list[tuple[float, str]]]:
    """Words grouped by baseline, each row sorted left to right."""
    out: dict[int, list[tuple[float, str]]] = {}
    for text, x, y in words(pdf):
        out.setdefault(round(y), []).append((x, text))
    for row in out.values():
        row.sort()
    return out


def first_x(pdf: Path) -> dict[str, float]:
    """x of the first occurrence of each word, in reading order."""
    out: dict[str, float] = {}
    for text, x, _y in sorted(words(pdf), key=lambda w: (w[2], w[1])):
        out.setdefault(text, x)
    return out
