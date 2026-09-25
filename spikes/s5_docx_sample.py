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
r"""Build the .docx sample that WORD-TESTS-TODO.md asks someone to open.

    python3 spikes/s5_docx_sample.py [OUTDIR]        # default: /tmp

This is NOT the converter emitting .docx -- it cannot, which is the point of
plan-docx.md.  It hand-assembles the OOXML a `--to docx` emitter *would*
write, so that opening the result in Word tests the plan and not
LibreOffice's exporter.  Re-saving a converted .odt as .docx would test the
exporter instead, which is a different and much less interesting question.

Every number is written with a cached value of 1 and every reference with a
cached 99, deliberately: a reader who sees (1) and (2) with matching
references has watched the fields recalculate, which is the premise the
whole target rests on.

The column widths come from the converter's own estimator, with a fudge:
_ADVANCE is Liberation Serif at 12pt and pandoc's reference.docx is neither,
so the raw numbers are about a third too narrow.  Fact 10 of plan-docx.md;
the emitter will have to settle it properly rather than multiply by 1.35.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from linguexx2odt.emit_odt import text_width_cm      # noqa: E402
from linguexx2odt.styles import Layout               # noqa: E402

DXA = 566.93          #: twentieths of a point per centimetre
TEXT_W = 16.0         #: pandoc's default docx text block, in cm
FUDGE = 1.35          #: see the module docstring, and fact 10

LAY = Layout()


def field(instr: str, cached: object, bm: str | None = None, bid: int = 1) -> str:
    r"""A Word field: begin, instruction, cached result, end.

    The bookmark, when given, wraps ONLY the field.  Wrapping the paragraph
    makes \ref give back the whole line -- fact 3 of plan-docx.md, and the
    difference between "See (3)" and "See (3) ALPHA".
    """
    start = f'<w:bookmarkStart w:id="{bid}" w:name="{bm}"/>' if bm else ""
    end = f'<w:bookmarkEnd w:id="{bid}"/>' if bm else ""
    return (
        start
        + '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        + f'<w:r><w:instrText xml:space="preserve"> {instr} </w:instrText></w:r>'
        + '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        + f"<w:r><w:t>{cached}</w:t></w:r>"
        + '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
        + end
    )


def cell(width_cm: float, runs: str, span: int = 1) -> str:
    grid = f'<w:gridSpan w:val="{span}"/>' if span > 1 else ""
    return (
        f'<w:tc><w:tcPr><w:tcW w:w="{int(width_cm * DXA)}" w:type="dxa"/>{grid}</w:tcPr>'
        f"<w:p>{runs}</w:p></w:tc>"
    )


def example(tiers: list[list[str]], translation: str, bm: str, bid: int) -> str:
    """One glossed example as a table, laid out the way the emitter would."""
    n = max(len(t) for t in tiers)
    cols = [
        max((text_width_cm(t[i], LAY.em_cm) if i < len(t) else 0) for t in tiers)
        * FUDGE
        + LAY.pad_cm
        for i in range(n)
    ]
    widths = [LAY.number_cm] + cols
    # The table spans the text block and parks the slack in a trailing
    # filler column.  Fact 9: a narrow table rendered at 69% of its declared
    # widths, and this is the rule the ODT emitter already follows.
    widths.append(TEXT_W - sum(widths))

    grid = "".join(f'<w:gridCol w:w="{int(w * DXA)}"/>' for w in widths)
    rows = []
    for t, words in enumerate(tiers):
        number = (
            '<w:r><w:t>(</w:t></w:r>'
            + field("SEQ NumEx \\* ARABIC", 1, bm, bid)
            + "<w:r><w:t>)</w:t></w:r>"
        )
        cells = [cell(widths[0], number if t == 0 else "")]
        for i in range(n):
            word = words[i] if i < len(words) else ""
            cells.append(cell(widths[i + 1], f'<w:r><w:t xml:space="preserve">{word}</w:t></w:r>'))
        cells.append(cell(widths[-1], ""))
        rows.append("<w:tr>" + "".join(cells) + "</w:tr>")

    rows.append(
        "<w:tr>"
        + cell(widths[0], "")
        + cell(sum(widths[1:]), f"<w:r><w:t>{translation}</w:t></w:r>", span=n + 1)
        + "</w:tr>"
    )

    # Zeroed cell margins: OOXML insets content by 108 twips a side and the
    # width estimate knows nothing about it.  Fact 8.
    return (
        f'<w:tbl><w:tblPr><w:tblW w:w="{int(TEXT_W * DXA)}" w:type="dxa"/>'
        '<w:tblLayout w:type="fixed"/>'
        "<w:tblCellMar>"
        '<w:top w:w="0" w:type="dxa"/><w:left w:w="0" w:type="dxa"/>'
        '<w:bottom w:w="0" w:type="dxa"/><w:right w:w="0" w:type="dxa"/>'
        "</w:tblCellMar></w:tblPr>"
        f"<w:tblGrid>{grid}</w:tblGrid>" + "".join(rows) + "</w:tbl>"
    )


PREAMBLE = """# linguexx → .docx feasibility sample

Not produced by the converter — it cannot emit .docx yet. This is the OOXML
a `--to docx` emitter *would* write: live `SEQ` numbers, `REF` references, a
fixed table grid whose widths come from the converter's own estimator.

**What to look for.**

1. Every number and reference below is written with a deliberately wrong
   cached value — the examples cache `1`, the references cache `99`. If Word
   shows **(1)** and **(2)** and the references agree with them, the fields
   are live and the premise of the whole target holds.
2. If Word shows `99` instead, press F9 (or Ctrl+A then F9). That would mean
   the fields work but must be written already-correct at build time, which
   is a small change to the plan rather than a problem.
3. Please say whether Word offers to **repair** the file when it opens.
   LibreOffice is forgiving about OOXML and Word is not, and that is the one
   risk in plan-docx.md that nothing here can test.
"""


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp")
    out.mkdir(parents=True, exist_ok=True)

    ex1 = example(
        [["que", "Pierre", "est", "fatigué"], ["that", "Pierre", "is", "tired"]],
        "‘that Pierre is tired’", "exone", 1,
    )
    ex2 = example(
        [["il", "mio", "libro"], ["the", "my", "book"]],
        "‘my book’", "extwo", 2,
    )
    refs = (
        "Cross-references to (`" + field("REF exone \\h", 99) + "`{=openxml}"
        ") and (`" + field("REF extwo \\h", 99) + "`{=openxml}).\n"
    )

    md = out / "linguexx-docx-sample.md"
    md.write_text(
        PREAMBLE
        + f"\n```{{=openxml}}\n{ex1}\n```\n"
        + f"\n```{{=openxml}}\n{ex2}\n```\n\n"
        + refs,
        encoding="utf-8",
    )
    docx = out / "linguexx-docx-sample.docx"
    subprocess.run(["pandoc", "-f", "markdown", "-t", "docx",
                    str(md), "-o", str(docx)], check=True)
    print(f"wrote {docx}")
    print("Open it in Word; WORD-TESTS-TODO.md says what to look for.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
