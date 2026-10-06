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
"""The numbered equations of a converted file, read from its XML.

Not from a rendering: what text a PDF gives for a formula depends on the
LibreOffice that made it -- "a=b" here, "Formula-0" on CI's -- so a test
that read the equation back off the page tested the LibreOffice.  The
file says it outright: each LxEquation paragraph, whether it holds an
equation, and the number beside it.
"""

from __future__ import annotations

import re
from pathlib import Path

from linguexx2odt import postprocess


def equation_paragraphs(doc: Path) -> list[tuple[bool, str | None]]:
    """(holds an equation, its number or None), per LxEquation paragraph."""
    if doc.suffix == ".odt":
        xml = postprocess.read(doc, "content.xml")
        paras = re.findall(r'<text:p text:style-name="LxEquation">.*?</text:p>', xml, re.S)
        math = "<draw:object"
        text = [re.sub(r"<[^>]+>", "", re.sub(r"<draw:frame.*?</draw:frame>", "", p, flags=re.S))
                for p in paras]
    else:
        xml = postprocess.read(doc, "word/document.xml")
        paras = [p for p in re.findall(r"<w:p\b(?:(?!</w:p>).)*</w:p>", xml, re.S)
                 if 'w:val="LxEquation"' in p]
        math = "<m:oMath"
        text = ["".join(re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>",
                                   re.sub(r"<m:oMath.*?</m:oMath>", "", p, flags=re.S)))
                for p in paras]
    return [(math in p, t.strip() or None) for p, t in zip(paras, text)]


def math_objects(doc: Path) -> int:
    """Every equation in the file, numbered or not."""
    if doc.suffix == ".odt":
        return postprocess.read(doc, "content.xml").count("<draw:object")
    return len(re.findall(r"<m:oMath[ >]", postprocess.read(doc, "word/document.xml")))
