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
"""Check a .docx against the ECMA-376 transitional schemas.

    python3 tools/validate_docx.py FILE.docx [FILE.docx ...]

Run `tools/fetch_ooxml_schemas.py` once first.

**What this buys.** Word offers to *repair* a file whose markup it will not
accept, and a repair prompt teaches a user not to trust the tool — worse
than a wrong column width, which at least looks like a bug in a document.
LibreOffice is forgiving and will open things Word will not, so testing only
there says little. This says whether the markup conforms, which is most of
that risk, and it says it here rather than on somebody else's Windows.

**What it does not buy.** Schema-valid is not the same as Word-accepted.
Word enforces relationships, content types and part-level rules this does
not look at, and it has opinions of its own. A clean run here makes a repair
prompt unlikely; only Word makes it impossible. See WORD-TESTS-TODO.md.

It also says nothing about whether the document is *right* — a table with
its columns in the wrong order validates perfectly.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / ".ooxml-schemas"

#: part inside the .docx -> the schema its root element belongs to
PARTS = {
    "word/document.xml": "wml.xsd",
    "word/styles.xml": "wml.xsd",
    "word/numbering.xml": "wml.xsd",
    "word/settings.xml": "wml.xsd",
    "word/footnotes.xml": "wml.xsd",
    "word/endnotes.xml": "wml.xsd",
}


def validate(path: Path) -> list[str]:
    """Problems found in *path*, as readable lines.  Empty means clean."""
    from lxml import etree

    problems: list[str] = []
    cache: dict[str, object] = {}
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())

        # Well-formedness of every XML part, first: a part that will not
        # parse is a broken file whatever the schema would have said.
        for name in sorted(names):
            if not name.endswith((".xml", ".rels")):
                continue
            try:
                etree.fromstring(z.read(name))
            except etree.XMLSyntaxError as exc:
                problems.append(f"{name}: not well-formed XML: {exc}")

        for part, xsd in PARTS.items():
            if part not in names:
                continue
            if xsd not in cache:
                cache[xsd] = etree.XMLSchema(etree.parse(str(SCHEMAS / xsd)))
            schema = cache[xsd]
            try:
                doc = etree.fromstring(z.read(part))
            except etree.XMLSyntaxError:
                continue                      # already reported above
            if not schema.validate(doc):
                for err in schema.error_log:
                    problems.append(f"{part}:{err.line}: {err.message}")
    return problems


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    if not (SCHEMAS / "wml.xsd").is_file():
        print(f"no schemas in {SCHEMAS}.\n"
              f"Run: python3 tools/fetch_ooxml_schemas.py", file=sys.stderr)
        return 2
    try:
        import lxml  # noqa: F401
    except ImportError:
        print("lxml is needed to validate; install python-lxml", file=sys.stderr)
        return 2

    bad = 0
    for arg in argv:
        path = Path(arg)
        problems = validate(path)
        if problems:
            bad += 1
            print(f"FAIL {path.name}: {len(problems)} problem(s)")
            for line in problems[:20]:
                print(f"    {line}")
            if len(problems) > 20:
                print(f"    ... and {len(problems) - 20} more")
        else:
            print(f"ok   {path.name}: every XML part well-formed and schema-valid")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
