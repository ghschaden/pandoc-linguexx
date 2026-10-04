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
r"""Text linguexx prints and the converter did not.

Three cases, found by the way back (plan-reverse.md): reading a converted
document back and comparing it with the original showed what had never
reached the file.

* the text between ``\ex.`` and the first ``\a.`` -- dropped by the
  parser, with no warning;
* the text before a ``\gll`` -- the run said "kept as body text", and
  neither emitter writes a body's text when it has tiers;
* ``\a.\label{x}\sublabel{y}`` -- only the first was pulled, and the
  ``.docx`` showed the other to the reader as ``\label{x}``.

Where linguexx puts the first two was measured off its PDF; the tests here
hold the parse and the markup, which is what was wrong.
"""

from __future__ import annotations

import re

import pytest

from linguexx2odt.emit_base import emitter_for
from linguexx2odt.extract import parse


def doc(body: str) -> str:
    return "\\begin{document}\n" + body + "\n\n\\end{document}"


def markup(source: str, target: str) -> str:
    res = parse(source)
    em = emitter_for(target, brackets=res.brackets, labels=res.labels,
                     macros=res.macros)
    em.prepare(res.examples)
    return "".join(em.example(e) for e in res.examples)


def text_of(xml: str) -> str:
    """What a reader sees: a Word field's instruction is not text."""
    xml = re.sub(r"<w:instrText[^>]*>.*?</w:instrText>", "", xml, flags=re.S)
    return re.sub(r"<[^>]+>", "", xml)


HEAD = doc("\\ex. Square brackets around the number.\n\\a. sub one\n\\b. sub two")


def test_the_text_before_the_first_sub_example_is_kept() -> None:
    ex = parse(HEAD).examples[0]
    assert ex.head == "Square brackets around the number."
    assert [i.body.text for i in ex.items] == ["sub one", "sub two"]


@pytest.mark.parametrize("target", ["odt", "docx"])
def test_the_head_is_on_the_number_s_row(target: str) -> None:
    """On the number's row, across every column after it -- linguexx sets
    it from where the letters stand and wraps it at the block's edge -- and
    the first sub-example on a row of its own, without the number."""
    xml = markup(HEAD, target)
    row = "table:table-row" if target == "odt" else "w:tr"
    rows = [text_of(r) for r in re.findall(rf"<{row}>.*?</{row}>", xml, re.S)]
    assert rows[1] == "(1)Square brackets around the number."
    assert rows[2] == "a.sub one"


GLOSS = doc("\\ex. As Cicero puts it, \\gll magnam facultatem \\\\\n"
            "great ability \\\\\n`great skill'")


def test_the_text_before_a_gloss_is_its_first_column() -> None:
    res = parse(GLOSS)
    body = res.examples[0].body
    assert [t.cells for t in body.tiers] == [
        ("As Cicero puts it,", "magnam", "facultatem"),
        ("", "great", "ability")]
    assert body.text == ""
    assert not any("kept as body text" in w for w in res.warnings)


def test_a_judgment_and_text_before_a_gloss_stay_apart() -> None:
    """The mark goes to its column and the text stays a column of its own:
    looked for in the two at once, the text was glued to the first word."""
    body = parse(doc("\\ex. *As Cicero, \\gll a {b c}\\\\ x y\\\\")).examples[0].body
    assert body.judgment == "*"
    assert body.tiers[0].cells == ("As Cicero,", "a", "b c")


@pytest.mark.parametrize("target", ["odt", "docx"])
def test_the_text_before_a_gloss_is_in_the_file(target: str) -> None:
    assert "As Cicero puts it," in text_of(markup(GLOSS, target))


BOTH = doc("\\ex.\n\\a.\\label{cv:a}\\sublabel{cv:sa} CVA letter a.\n\\b. CVB.")


def test_label_and_sublabel_both_name_the_sub_example() -> None:
    res = parse(BOTH)
    assert res.labels["cv:a"] == res.labels["cv:sa"] == (0, "a")
    assert res.examples[0].items[0].body.text == "CVA letter a."


@pytest.mark.parametrize("target", ["odt", "docx"])
def test_no_label_is_printed(target: str) -> None:
    assert "label" not in text_of(markup(BOTH, target))
