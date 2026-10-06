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
r"""The pages a \pageref shows before anything updates its field.

A page is not known before layout, so a page field was written with "?"
as its cached value -- which is what a reader that does not update fields
shows (OnlyOffice, for a .docx).  When LibreOffice is there, the finished
file is laid out once: exported to PDF with its bookmarks as named
destinations, which say the page each bookmark is on, and the "?" become
those pages.  Word and LibreOffice still compute their own on update; a
reader that does not shows LibreOffice's layout, which is the one the
converter's columns were measured for.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import postprocess, postprocess_docx

_EXPORT = ('pdf:writer_pdf_Export:{"ExportBookmarksToPDFDestination":'
           '{"type":"boolean","value":"true"}}')

#: A page field still showing "?", by the bookmark it names.
_DOCX_PAGE = re.compile(
    r'(<w:instrText[^>]*> PAGEREF (\w+) \\h </w:instrText></w:r>'
    r'<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
    r'<w:r>(?:<w:rPr>.*?</w:rPr>)?<w:t[^>]*>)\?(</w:t>)', re.S)
_ODT_PAGE = re.compile(
    r'(<text:(?:bookmark-ref|sequence-ref|note-ref)\b[^>]*'
    r'text:reference-format="page"[^>]*text:ref-name="([^"]+)"[^>]*>)\?(</text:)')


def has_unknown_pages(xml: str) -> bool:
    return bool(_DOCX_PAGE.search(xml) or _ODT_PAGE.search(xml))


def bookmark_pages(doc: Path) -> dict[str, int] | None:
    """bookmark -> page, from LibreOffice's layout of *doc*; None if
    LibreOffice or pdfinfo is not there, or the export failed."""
    if shutil.which("soffice") is None or shutil.which("pdfinfo") is None:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        try:
            subprocess.run(["soffice", "--headless", "--convert-to", _EXPORT,
                            "--outdir", tmp, str(doc)],
                           check=True, capture_output=True, timeout=300)
            pdf = Path(tmp) / (doc.stem + ".pdf")
            listing = subprocess.run(["pdfinfo", "-dests", str(pdf)], check=True,
                                     capture_output=True, text=True, timeout=60).stdout
        except (subprocess.SubprocessError, OSError):
            return None
    pages: dict[str, int] = {}
    for m in re.finditer(r'^\s*(\d+)\s+\[[^\]]*\]\s+"([^"]*)"\s*$', listing, re.M):
        # LibreOffice writes a name's "_" as its hex code, "5F"
        name = re.sub(r"^5F", "_", m.group(2))
        pages.setdefault(name, int(m.group(1)))
    return pages


def fill(doc: Path, warn) -> None:
    """Put the pages in *doc*'s page fields, in place."""
    member = "word/document.xml" if doc.suffix == ".docx" else "content.xml"
    xml = postprocess.read(doc, member)
    if not has_unknown_pages(xml):
        return
    pages = bookmark_pages(doc)
    if pages is None:
        warn("page references show \"?\" until the word processor updates its fields: "
             "filling them in needs LibreOffice and pdfinfo")
        return
    pattern = _DOCX_PAGE if member == "word/document.xml" else _ODT_PAGE

    def page(m: re.Match[str]) -> str:
        found = pages.get(m.group(2))
        return f"{m.group(1)}{found if found is not None else '?'}{m.group(3)}"
    filled = pattern.sub(page, xml)
    if filled != xml:
        tmp = doc.with_name(doc.stem + ".pages" + doc.suffix)
        (postprocess_docx if doc.suffix == ".docx" else postprocess).rewrite(
            doc, tmp, {member: filled})
        tmp.replace(doc)
