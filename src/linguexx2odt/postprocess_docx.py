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


def apply_styles(raw: Path, out: Path, fragment: str) -> None:
    """Write *raw* to *out* with the style fragment added to styles.xml."""
    from .styles_docx import inject_styles

    if not fragment:
        shutil.copy2(raw, out)
        return
    styles = inject_styles(read(raw, "word/styles.xml"), fragment)
    rewrite(raw, out, {"word/styles.xml": styles})
