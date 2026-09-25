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
"""Patch a finished .docx: the styles an example is built from.

Smaller than the ODT pass, and the difference is worth stating.  ODF also
needs its sequence declaring and its automatic column styles carried,
because a raw block cannot hold them; OOXML needs neither -- a `SEQ` field
declares itself by being used, and a column's width lives in the cell.
What is left is the named styles, which both formats need for the same
reason: so that a user can change how every example looks from one place.

A separate rewrite from the ODT one because the archives differ.  ODF puts
an uncompressed `mimetype` first and the ODT pass asserts it; a .docx has
no such member and its first entry is ordinarily `[Content_Types].xml`.
Asserting the ODF shape here would refuse every valid Word file.
"""

from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path


def read(docx: Path, name: str) -> str:
    with zipfile.ZipFile(docx) as z:
        return z.read(name).decode("utf-8")


def rewrite(docx: Path, out: Path, members: dict[str, str]) -> None:
    """Copy *docx* to *out*, replacing the named members.

    Every other entry is copied with its compression as it was found, so
    that what comes out differs from what went in only where it was meant
    to.
    """
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(docx) as src, \
            zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = members.get(info.filename)
            if data is None:
                dst.writestr(info, src.read(info.filename))
            else:
                dst.writestr(info, data.encode("utf-8"))


def set_default_font(styles_xml: str, run_props: str) -> str:
    r"""Make the document's default run the face the columns were measured for.

    The columns come from `measure._ADVANCE`, which is Liberation Serif
    metrics.  pandoc's reference.docx points its default at a *theme* font
    (`w:asciiTheme="minorHAnsi"`), which resolves to something narrower, so
    words wrapped inside columns sized for something else.

    The face belongs on the document default and not on the example style.
    Put it on the style and the examples come out in a different face from
    the prose around them -- which the ODT target never does, its
    LxExampleCell inheriting from Standard and naming no font.

    **Replaces** the existing `w:rFonts` and sizes rather than inserting
    beside them.  Prepending looked right and did nothing: pandoc's theme
    rFonts followed mine inside the same `w:rPr` and won, and the check
    that was supposed to notice looked for `w:ascii=` where pandoc writes
    `w:asciiTheme=`.
    """
    m = re.search(r"(<w:rPrDefault>\s*<w:rPr>)(.*?)(</w:rPr>)", styles_xml, re.S)
    if not m:
        return styles_xml
    inner = m.group(2)
    for tag in ("w:rFonts", "w:sz", "w:szCs"):
        inner = re.sub(rf"<{tag}\b[^>]*/>", "", inner)
    return (styles_xml[:m.start()] + m.group(1) + run_props + inner
            + m.group(3) + styles_xml[m.end():])


def apply_styles(raw: Path, out: Path, fragment: str,
                 default_run_props: str = "") -> None:
    """Write *raw* to *out* with the styles added and the face declared."""
    from .styles_docx import inject_styles

    if not fragment and not default_run_props:
        shutil.copy2(raw, out)
        return
    styles = read(raw, "word/styles.xml")
    styles = inject_styles(styles, fragment)
    if default_run_props:
        styles = set_default_font(styles, default_run_props)
    rewrite(raw, out, {"word/styles.xml": styles})
