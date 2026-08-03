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

"""S2 — do NumEx number-range fields and their cross-references evaluate?

Two variants are built: with and without an injected
``<text:sequence-decls>`` naming NumEx, to learn whether LibreOffice
tolerates an undeclared sequence.

The cached values inside the fields are deliberately WRONG ("99"), so the
PDF can only show 1 / 2 / 1 if LibreOffice really evaluated the formula
rather than echoing our text.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import odtzip  # noqa: E402

HERE = Path(__file__).parent
OUT = odtzip.fresh(HERE / "_out" / "s2")


def seq(ref: str) -> str:
    return (
        f'<text:sequence text:ref-name="{ref}" text:name="NumEx"'
        ' text:formula="ooow:NumEx+1" style:num-format="1">99</text:sequence>'
    )


def seqref(ref: str) -> str:
    return (
        f'<text:sequence-ref text:reference-format="value"'
        f' text:ref-name="{ref}">99</text:sequence-ref>'
    )


RAW = (
    f'<text:p text:style-name="Standard">({seq("refNumEx0")})<text:tab/>'
    "Alpha is the first example.</text:p>\n"
    f'<text:p text:style-name="Standard">({seq("refNumEx1")})<text:tab/>'
    "Beta is the second example.</text:p>\n"
    f'<text:p text:style-name="Standard">Backref to ({seqref("refNumEx0")}) '
    f"and forward to ({seqref('refNumEx1')}).</text:p>"
)


def build(name: str, *, decls: bool) -> Path:
    doc = {
        "pandoc-api-version": [1, 23, 1],
        "meta": {},
        "blocks": [
            {"t": "Para", "c": [{"t": "Str", "c": "Prose."}]},
            {"t": "RawBlock", "c": ["opendocument", RAW]},
        ],
    }
    src = OUT / f"{name}.json"
    src.write_text(json.dumps(doc), encoding="utf-8")
    raw_odt = OUT / f"{name}_raw.odt"
    subprocess.run(["pandoc", "-f", "json", str(src), "-o", str(raw_odt)], check=True)

    content = odtzip.read_member(raw_odt, "content.xml")
    if decls:
        content = odtzip.inject_sequence_decls(content)
    odt = OUT / f"{name}.odt"
    odtzip.patch(raw_odt, odt, {"content.xml": content})
    return odt


def check(odt: Path) -> tuple[bool, str]:
    pdf = odtzip.soffice_convert(odt, "pdf", OUT)
    text = odtzip.pdf_text(pdf)
    (OUT / (odt.stem + ".txt")).write_text(text, encoding="utf-8")
    ok = (
        "(1)" in text
        and "(2)" in text
        and "99" not in text
        and "Backref to (1) and forward to (2)." in " ".join(text.split())
    )
    return ok, " ".join(text.split())[:160]


def main() -> int:
    rc = 0
    for name, decls in (("with_decls", True), ("without_decls", False)):
        odt = build(name, decls=decls)
        fodt = odtzip.soffice_convert(odt, "fodt", OUT)
        round_tripped = fodt.read_text(encoding="utf-8")
        fields_survive = (
            'text:name="NumEx"' in round_tripped
            and "<text:sequence-ref" in round_tripped
        )
        ok, sample = check(odt)
        rc |= 0 if ok else 1
        print(f"[{name}]")
        print(f"  fields survive LO round-trip : {fields_survive}")
        print(f"  numbers evaluate in PDF      : {ok}")
        print(f"  pdf text                     : {sample}")
        if decls:
            decl_kept = "NumEx" in round_tripped.split("</text:sequence-decls>")[0]
            print(f"  NumEx present in decls       : {decl_kept}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
