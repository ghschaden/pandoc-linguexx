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

"""The converter's own table plans for the typed-line fixtures -- the
answers the JavaScript add-in core (addin/core/plan.js) is held to.

    python3 tools/addin_oracle.py            # check, exit 1 on drift
    python3 tools/addin_oracle.py --write    # rewrite the goldens

Each fixture's *parse* is the Writer macro's, recorded in
tests/fixtures/typed-examples.json.  This builds the converter's IR from
that parse, runs BaseEmitter.prepare() and plan_table() on it -- the code
every .odt and .docx the converter writes is laid out by -- and records
the result in tests/fixtures/typed-examples.plans.json.  addin/core's
test/plan.test.js then requires planTable to give the same bands, spans
and widths exactly: the arithmetic is ported, not approximated, so there is
no tolerance to hide a difference in.

Three text widths: A4's 17 cm, 12 cm so that more of the fixtures band,
and 7 cm -- a column of a two-column page -- where a word capped at
max_col_cm is still wider than the space left for words, which is the only
place the guard against an empty band and the squeezed-annotation gap are
reached at all.  Cells are LaTeX to the
converter, so typed text is escaped -- and then read back through the
converter's own InlineRenderer and required to come out as typed, because
a straight quote the converter would draw curly, or "--" it would draw as
an en dash, is a different example, not the same one measured twice.
tests/test_addin_core.py runs the check.

A second golden, typed-examples.docx.json, holds what DocxEmitter.example()
writes for the same examples: the w:tbl the Word add-in's ooxml.js must
reproduce string for string.  The translation is recorded as the converter
DRAWS it, because LaTeX turns a typed ' into a curly quote and the add-in
leaves what the linguist typed alone -- so the add-in's test is given the
drawn text, and the comparison is of markup, not of quote conventions.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from linguexx2odt.emit_base import BaseEmitter  # noqa: E402
from linguexx2odt.emit_docx import DocxEmitter  # noqa: E402
from linguexx2odt.inline import InlineRenderer  # noqa: E402
from linguexx2odt.ir import Body, Example, Item, Tier  # noqa: E402
from linguexx2odt.styles import Layout  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "typed-examples.json"
GOLDEN = ROOT / "tests" / "fixtures" / "typed-examples.plans.json"
DOCX_GOLDEN = ROOT / "tests" / "fixtures" / "typed-examples.docx.json"
TEXT_WIDTHS = (17.0, 12.0, 7.0)

#: Faces besides Times, each at 17 cm: the widths must follow the face, and
#: the core is held to the converter's own advances_for() for it.
FACES = ("Aptos",)

_SPECIAL = {
    "\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "%": r"\%", "#": r"\#",
    "&": r"\&", "$": r"\$", "_": r"\_", "^": r"\^{}",
}


class NotTheSameText(Exception):
    """Typed text the converter would read as something else."""


def latex(text: str, where: str) -> str:
    """*text* as LaTeX the converter reads back as exactly *text*."""
    out = "".join(_SPECIAL.get(c, c) for c in text)
    back = "".join(t for t, _ in InlineRenderer(lambda _m: None).runs(out))
    if back != text:
        raise NotTheSameText(
            f"{where}: typed {text!r} reads back from LaTeX as {back!r}; "
            f"the converter and the add-in would be measuring different "
            f"text, so this fixture cannot be compared -- change its words")
    return out


def body(item: dict, where: str) -> Body:
    tiers = item["tiers"]
    glossed = len(tiers) > 1
    return Body(
        judgment=latex(item["judgment"], where),
        text=latex(" ".join(tiers[0]), where) if tiers and not glossed else "",
        tiers=tuple(Tier(tuple(latex(w, where) for w in t)) for t in tiers) if glossed else (),
        translation=item["translation"],   # not measured; kept as typed
        annot=latex(item["annot"], where),
    )


def example(parse: dict, where: str) -> Example:
    items = parse["items"]
    if len(items) == 1 and not items[0]["marker"]:
        return Example(index=0, placeholder="", body=body(items[0], where))
    return Example(index=0, placeholder="", items=tuple(
        Item(level=1, ordinal=k, marker=latex(it["marker"], where),
             body=body(it, where))
        for k, it in enumerate(items)))


def plan(ex: Example, text_width: float, face: str = "Times New Roman") -> dict:
    em = BaseEmitter(layout=Layout(text_width_cm=text_width, font_name=face))
    em.prepare([ex])
    p = em.plan_table(ex)
    lay = em.layout
    return {
        "prepared": {"number_cm": lay.number_cm, "marker_cm": lay.marker_cm,
                     "judgment_cm": lay.judgment_cm,
                     "any_judgment": em.any_judgment},
        "lead": p.lead, "columns": p.columns, "widths": p.widths,
        "filler": p.filler, "has_marker": p.has_marker,
        "has_judgment": p.has_judgment, "has_annot": p.has_annot,
        "bands": [list(map(list, p.grid.bands_of(k))) for k in range(len(p.bodies))],
        "placement": [
            [list(p.grid._placement[(k, j)]) for j in range(len(w))]
            for k, (w, _) in enumerate(p.grid.plans)
        ],
        "warnings": em.warnings,
    }


def golden() -> dict:
    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))
    out = {"_about": [
        "GENERATED by tools/addin_oracle.py -- the converter's plan_table() on",
        "the macro's parse of each typed-line fixture, at each text width.",
        "addin/core/test/plan.test.js requires the JavaScript core to agree",
        "exactly.  Regenerate with --write, and read the diff first.",
    ]}
    for key, parse in fixtures["parsed"].items():
        if "error" in parse:
            continue
        ex = example(parse, key)
        out[key] = {f"{w:g}": plan(ex, w) for w in TEXT_WIDTHS}
        out[key].update({f"17 {face}": plan(ex, 17.0, face) for face in FACES})
    return out


def docx(ex: Example, text_width: float) -> dict:
    em = DocxEmitter(layout=Layout(text_width_cm=text_width))
    em.prepare([ex])
    drawn = ["".join(t for t, _ in em.inline.runs(b.translation)) for b in ex.bodies]
    return {"table": em.example(ex), "translations_drawn": drawn}


def docx_golden() -> dict:
    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))
    out = {"_about": [
        "GENERATED by tools/addin_oracle.py -- the converter's DocxEmitter.example()",
        "on the macro's parse of each typed-line fixture, at each text width, and",
        "each body's translation as the converter draws it.  addin/word's",
        "test/ooxml.test.js requires the Word add-in's markup to be the same.",
    ]}
    for key, parse in fixtures["parsed"].items():
        if "error" in parse:
            continue
        ex = example(parse, key)
        out[key] = {f"{w:g}": docx(ex, w) for w in TEXT_WIDTHS}
    return out


def render(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1) + "\n"


def main(argv: list[str]) -> int:
    drifted = 0
    for path, make, what in ((GOLDEN, golden, "plan_table()"),
                             (DOCX_GOLDEN, docx_golden, "DocxEmitter")):
        want = render(make())
        have = path.read_text(encoding="utf-8") if path.is_file() else ""
        if have == want:
            print(f"{path.name}: in sync with the converter's {what}")
        elif "--write" in argv:
            path.write_text(want, encoding="utf-8")
            print(f"{path.name}: rewritten -- read the diff before committing it")
        else:
            print(f"{path.relative_to(ROOT)} no longer matches the converter's "
                  f"{what}; run tools/addin_oracle.py --write and read the diff")
            drifted += 1
    return 1 if drifted else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
