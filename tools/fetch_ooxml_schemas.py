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
"""Fetch the ECMA-376 schemas a .docx has to validate against.

    python3 tools/fetch_ooxml_schemas.py

into `.ooxml-schemas/`, which is gitignored: 968 KB of somebody else's
standard, cached rather than vendored so that putting it in the repository
stays a decision somebody takes rather than one this script took for them.

**Transitional, not Strict, and the difference is the whole point.**  The
5th edition's Part 1 ships the Strict schemas, whose namespace is
`purl.oclc.org/ooxml/...`.  pandoc writes Transitional, whose namespace is
`schemas.openxmlformats.org/.../2006/main`, as does every .docx Word has
ever saved by default.  Validating one against the other fails on the
namespace before it reaches anything real, which looks like a catastrophic
result and means nothing.  The Transitional schemas are in **Part 4**,
"Transitional Migration Features", and nowhere else.

One local edit is made after unpacking: `wml.xsd` uses `xml:space` without
importing the namespace that declares it, so libxml2 refuses to build the
schema at all ("The QName value '{...XML/1998/namespace}space' does not
resolve").  The import is added, pointing at a local copy of the W3C's
`xml.xsd`.  That is a fix to a published schema, which is worth saying out
loud; it adds a declaration the document already relies on and changes
nothing that is validated.
"""

from __future__ import annotations

import io
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / ".ooxml-schemas"

PART4 = ("https://ecma-international.org/wp-content/uploads/"
         "ECMA-376-4_5th_edition_december_2016.zip")
INNER = "OfficeOpenXML-XMLSchema-Transitional.zip"
XML_XSD = "https://www.w3.org/2001/xml.xsd"


def fetch(url: str) -> bytes:
    print(f"  fetching {url}")
    with urllib.request.urlopen(url, timeout=120) as r:   # noqa: S310
        return r.read()


def main() -> int:
    if (DEST / "wml.xsd").is_file():
        print(f"already present in {DEST}; delete it to refetch")
        return 0
    DEST.mkdir(parents=True, exist_ok=True)

    outer = zipfile.ZipFile(io.BytesIO(fetch(PART4)))
    if INNER not in outer.namelist():
        print(f"{INNER} is not in Part 4 any more; contents: {outer.namelist()}",
              file=sys.stderr)
        return 2
    inner = zipfile.ZipFile(io.BytesIO(outer.read(INNER)))
    inner.extractall(DEST)
    print(f"  {len(list(DEST.glob('*.xsd')))} schemas in {DEST}")

    (DEST / "xml.xsd").write_bytes(fetch(XML_XSD))

    wml = DEST / "wml.xsd"
    text = wml.read_text(encoding="utf-8")
    if 'schemaLocation="xml.xsd"' not in text:
        m = re.search(r"<xsd:schema[^>]*>", text)
        if not m:
            print("wml.xsd has no <xsd:schema> element?", file=sys.stderr)
            return 2
        imp = ('<xsd:import namespace="http://www.w3.org/XML/1998/namespace" '
               'schemaLocation="xml.xsd"/>')
        wml.write_text(text[:m.end()] + imp + text[m.end():], encoding="utf-8")
        print("  added the xml: namespace import wml.xsd relies on and omits")

    # Prove it builds, here, rather than leaving the first user to find out.
    try:
        from lxml import etree
    except ImportError:
        print("  (lxml not installed; schemas fetched but not checked)")
        return 0
    etree.XMLSchema(etree.parse(str(wml)))
    print("  wml.xsd builds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
