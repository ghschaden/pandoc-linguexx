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

"""S1 — does raw ``opendocument`` survive pandoc -> odt verbatim?

Re-run whenever the pandoc version changes.  Checks the three constructs the
emitter depends on: text:sequence, text:sequence-ref, and a table with
number-columns-spanned + covered-table-cell.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import odtzip  # noqa: E402

HERE = Path(__file__).parent
OUT = odtzip.fresh(HERE / "_out" / "s1")

RAW = """\
<text:p text:style-name="Standard">(<text:sequence text:ref-name="refNumEx0"\
 text:name="NumEx" text:formula="ooow:NumEx+1" style:num-format="1">1</text:sequence>)\
\t<text:tab/>Raw passthrough example.</text:p>
<text:p text:style-name="Standard">See (<text:sequence-ref\
 text:reference-format="value" text:ref-name="refNumEx0">1</text:sequence-ref>).</text:p>
<table:table table:name="LxEx1" table:style-name="LxExTable">
<table:table-column table:style-name="LxExCol.A"/>
<table:table-column table:style-name="LxExCol.B" table:number-columns-repeated="2"/>
<table:table-row>
<table:table-cell office:value-type="string"><text:p>(2)</text:p></table:table-cell>
<table:table-cell table:number-columns-spanned="2" office:value-type="string">\
<text:p>merged translation</text:p></table:table-cell>
<table:covered-table-cell/>
</table:table-row>
</table:table>"""

MD = f"""\
Some prose before.

```{{=opendocument}}
{RAW}
```

Some prose after.
"""


def via_json(odt: Path) -> None:
    """The path the real pipeline uses: AST JSON -> odt."""
    doc = {
        "pandoc-api-version": [1, 23, 1],
        "meta": {},
        "blocks": [
            {"t": "Para", "c": [{"t": "Str", "c": "Before."}]},
            {"t": "RawBlock", "c": ["opendocument", RAW]},
            {"t": "Para", "c": [{"t": "Str", "c": "After."}]},
        ],
    }
    src = OUT / "s1.json"
    src.write_text(json.dumps(doc), encoding="utf-8")
    subprocess.run(["pandoc", "-f", "json", str(src), "-o", str(odt)], check=True)


def main() -> int:
    version = subprocess.run(
        ["pandoc", "--version"], check=True, capture_output=True, text=True
    ).stdout.splitlines()[0]

    # (a) markdown reader, for the record
    src = OUT / "s1.md"
    src.write_text(MD, encoding="utf-8")
    md_odt = OUT / "s1_md.odt"
    subprocess.run(["pandoc", str(src), "-o", str(md_odt)], check=True)
    md_content = odtzip.read_member(md_odt, "content.xml")
    md_exact = all(
        ln in md_content for ln in RAW.splitlines() if ln.strip()
    )

    # (b) json reader — the real pipeline
    odt = OUT / "s1.odt"
    via_json(odt)
    content = odtzip.read_member(odt, "content.xml")

    failures = []
    for line in RAW.splitlines():
        if line.strip() and line not in content:
            failures.append(line[:90])

    # namespaces the emitter needs, declared on the root by pandoc itself
    root = content[: content.index(">") + 1]
    for ns in ("xmlns:table=", "xmlns:text=", "xmlns:style=", "xmlns:fo=", "xmlns:office="):
        if ns not in content[: content.index("<office:body")]:
            failures.append(f"missing namespace {ns}")

    has_decls = "<text:sequence-decls" in content
    (OUT / "content.xml").write_text(content, encoding="utf-8")

    print(f"pandoc: {version}")
    print(f"markdown reader passthrough exact: {md_exact}")
    print(f"raw lines preserved verbatim: {'YES' if not failures else 'NO'}")
    print(f"content.xml already carries text:sequence-decls: {has_decls}")
    print(f"root element: {root[:60]}...")
    for f in failures:
        print(f"  FAIL: {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
