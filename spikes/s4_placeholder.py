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

"""S4 — pandoc JSON round-trip for the placeholder paragraphs.

Checks that a placeholder emitted by extract.py:
  * comes back as a Para of its own (never merged into a neighbour),
  * survives every awkward position (document start/end, right after a
    section heading, two in a row, inside itemize, inside a footnote),
  * is textually recoverable from the AST.

Also records how pandoc 3.6.1 represents \\ref{...}, which inject.py must
rewrite into a text:sequence-ref.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import odtzip  # noqa: E402

HERE = Path(__file__).parent
OUT = odtzip.fresh(HERE / "_out" / "s4")

PLACEHOLDERS = {
    "unicode": "⟨⟨LINGUEXX-{n:04d}⟩⟩",
    "ascii": "LINGUEXXPLACEHOLDER{n:04d}ENDLINGUEXX",
}


def residue(fmt: str) -> str:
    p = [fmt.format(n=i) for i in range(9)]
    return rf"""\documentclass{{article}}
\usepackage{{linguexx}}
\begin{{document}}

{p[0]}

Opening prose after the very first example.

\section{{A section}}

{p[1]}

{p[2]}

Two examples in a row precede this paragraph, and we refer to
\ref{{ex:first}} and to \ref{{ex:second}} here.

\begin{{itemize}}
\item A list item containing {p[3]} inline.
\item Another item.
\end{{itemize}}

A paragraph with a footnote.\footnote{{Footnote text with {p[4]} inside.}}

\subsection{{Immediately followed}}
{p[5]}

Prose that immediately follows without a blank line before the example:
{p[6]}
and continues right after it.

\emph{{Emphasised prose}} then {p[7]} then more.

{p[8]}
\end{{document}}
"""


def texts(node: dict) -> str:
    """Concatenate the plain text of an inline list."""
    out = []
    stack = list(node if isinstance(node, list) else [node])
    while stack:
        n = stack.pop(0)
        if not isinstance(n, dict):
            continue
        t, c = n.get("t"), n.get("c")
        if t == "Str":
            out.append(c)
        elif t == "Space":
            out.append(" ")
        elif t in ("SoftBreak", "LineBreak"):
            out.append(" ")
        elif isinstance(c, list):
            stack = [x for x in c if isinstance(x, dict)] + stack
        elif t == "Link" or t == "Span":
            pass
    return "".join(out)


def walk(blocks, depth=0):
    for b in blocks:
        if not isinstance(b, dict):
            continue
        yield depth, b
        c = b.get("c")
        for sub in (c if isinstance(c, list) else []):
            if isinstance(sub, list) and sub and isinstance(sub[0], dict) and "t" in sub[0]:
                yield from walk(sub, depth + 1)
            elif isinstance(sub, list):
                for s2 in sub:
                    if isinstance(s2, list):
                        yield from walk(s2, depth + 1)


def analyse(kind: str, fmt: str) -> dict:
    tex = OUT / f"{kind}.tex"
    tex.write_text(residue(fmt), encoding="utf-8")
    js = subprocess.run(
        ["pandoc", "-f", "latex", "-t", "json", str(tex)],
        check=True, capture_output=True, text=True,
    ).stdout
    (OUT / f"{kind}.json").write_text(js, encoding="utf-8")
    doc = json.loads(js)

    pat = re.compile(re.escape(fmt.format(n=0)).replace("0000", r"(\d{4})"))
    found, alone, contaminated = {}, {}, {}
    for depth, b in walk(doc["blocks"]):
        if b.get("t") not in ("Para", "Plain"):
            continue
        s = texts(b["c"])
        for m in pat.finditer(s):
            n = int(m.group(1))
            found[n] = depth
            alone[n] = s.strip() == m.group(0)
            if not alone[n]:
                contaminated[n] = s.strip()[:70]

    refs = [
        b for _, b in walk(doc["blocks"])
        for b in [b] if b.get("t") in ("Para", "Plain")
    ]
    ref_repr = set()
    stack = list(doc["blocks"])
    while stack:
        n = stack.pop()
        if isinstance(n, dict):
            if n.get("t") in ("Link", "RawInline", "Cite", "Span"):
                ref_repr.add(json.dumps(n)[:200])
            stack.extend(v for v in n.values() if isinstance(v, (list, dict)))
        elif isinstance(n, list):
            stack.extend(n)

    return {
        "found": sorted(found),
        "missing": [i for i in range(9) if i not in found],
        "own_para": sorted(i for i in found if alone[i]),
        "contaminated": contaminated,
        "depths": found,
        "ref_nodes": [r for r in ref_repr if "ex:" in r],
    }


def main() -> int:
    rc = 0
    for kind, fmt in PLACEHOLDERS.items():
        r = analyse(kind, fmt)
        print(f"[{kind}]  found {len(r['found'])}/9   own Para: {len(r['own_para'])}/9")
        if r["missing"]:
            print(f"  MISSING (mangled by the reader): {r['missing']}")
            rc = 1
        for n, s in sorted(r["contaminated"].items()):
            print(f"  #{n} shares its paragraph: {s!r}")
        print(f"  block depth per placeholder: {r['depths']}")
        if kind == "ascii":
            print("  \\ref representation:")
            for r0 in sorted(r["ref_nodes"]):
                print(f"    {r0}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
