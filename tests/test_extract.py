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

"""Golden tests for the parser.

Each ``tests/cases/*.tex`` is parsed and its IR compared with the snapshot
in ``tests/golden/*.json``.  Regenerate deliberately, never reflexively:

    LINGUEXX_UPDATE_GOLDEN=1 pytest tests/test_extract.py

A golden that records a bug is worse than no golden, so every snapshot in
``tests/golden`` was read by hand before being committed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from linguexx2odt.extract import PLACEHOLDER_RE, parse
from linguexx2odt.ir import to_json

HERE = Path(__file__).parent
CASES = sorted((HERE / "cases").glob("*.tex"))
GOLDEN = HERE / "golden"
CORPUS = Path(__file__).resolve().parents[2] / "linguexx" / "tests"

UPDATE = os.environ.get("LINGUEXX_UPDATE_GOLDEN") == "1"


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.stem)
def test_golden_ir(case: Path) -> None:
    result = parse(case.read_text(encoding="utf-8"))
    actual = json.loads(to_json(result.examples))
    payload = {
        "examples": actual,
        "labels": {k: list(v) for k, v in result.labels.items()},
        "warnings": result.warnings,
    }
    snap = GOLDEN / (case.stem + ".json")
    if UPDATE:
        snap.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        pytest.skip(f"golden updated: {snap.name}")
    assert snap.exists(), f"no golden for {case.name}; run with LINGUEXX_UPDATE_GOLDEN=1"
    assert payload == json.loads(snap.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.stem)
def test_residue_has_one_placeholder_per_example(case: Path) -> None:
    result = parse(case.read_text(encoding="utf-8"))
    found = PLACEHOLDER_RE.findall(result.residue)
    assert [int(n) for n in found] == [e.index for e in result.examples]


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.stem)
def test_placeholders_stand_alone(case: Path) -> None:
    """S4's rule: a placeholder must be surrounded by blank lines, which is
    what makes pandoc hand it back as a Para of its own."""
    residue = parse(case.read_text(encoding="utf-8")).residue
    for m in PLACEHOLDER_RE.finditer(residue):
        before, after = residue[: m.start()], residue[m.end() :]
        assert before.endswith("\n\n"), f"{m.group(0)} not preceded by a blank line"
        assert after.startswith("\n\n"), f"{m.group(0)} not followed by a blank line"


# --------------------------------------------------------------------------
# corpus: the real linguexx test suite must never crash the parser
# --------------------------------------------------------------------------

CORPUS_FILES = sorted(CORPUS.glob("*.tex")) if CORPUS.is_dir() else []


@pytest.mark.skipif(not CORPUS_FILES, reason="../linguexx checkout not present")
@pytest.mark.parametrize("tex", CORPUS_FILES, ids=lambda p: p.stem)
def test_corpus_never_crashes(tex: Path) -> None:
    result = parse(tex.read_text(encoding="utf-8"))
    found = [int(n) for n in PLACEHOLDER_RE.findall(result.residue)]
    assert found == [e.index for e in result.examples]
    for ex in result.examples:
        assert ex.body is not None or ex.items, f"example {ex.index} parsed to nothing"


def test_verbatim_is_not_scanned() -> None:
    src = r"""\begin{document}
\begin{verbatim}
\ex. This must not be found.
\end{verbatim}
\ex. But this one must. \verb|\ex. nor this|

\end{document}"""
    result = parse(src)
    assert len(result.examples) == 1
    assert result.examples[0].body is not None
    assert "But this one must." in result.examples[0].body.text
    assert r"\verb|\ex. nor this|" in result.examples[0].body.text


def test_comments_do_not_leak_into_bodies() -> None:
    src = "\\begin{document}\n\\ex. Visible text.  % a trailing comment\n\n\\end{document}"
    result = parse(src)
    assert result.examples[0].body.text == "Visible text."


def test_a_label_in_the_first_sub_example_is_that_sub_example_s() -> None:
    r"""``\a. \label{s}`` named the whole example: the example's own label
    was searched for anywhere in it, and the first sub-example's is the
    first found.  linguexx prints \ref{s} as (1a)."""
    def labels(head: str) -> dict:
        return parse(f"\\begin{{document}}\n\\ex. {head}\\a. \\label{{s1}} A. "
                     "\\b. \\label{s2} B.\n\n\\end{document}").labels

    assert labels("") == {"s1": (0, "a"), "s2": (0, "b")}
    assert labels("\\label{whole} ") == {
        "whole": (0, ""), "s1": (0, "a"), "s2": (0, "b")}


@pytest.mark.parametrize("head", ["*\\gll ", "* \\gll ", "\\gll *", "\\jdg{\\dag}\\gll "])
def test_a_judgment_keeps_the_gloss_braces(head: str) -> None:
    r"""A judged gloss lost its braces: the object line was rejoined to look
    for the mark and split again, so ``{ccc ddd}`` became two words.
    linguexx sets it as one, with the gloss beneath its first letter
    (measured: "zzz" at x 207.99 under "ccc", "ddd" after it)."""
    body = parse(f"\\begin{{document}}\n\\ex. {head}aaa {{ccc ddd}} bbb\\\\\n"
                 "xxx zzz yyy\\\\\n\n\\end{document}").examples[0].body
    assert body.judgment
    assert body.tiers[0].cells == ("aaa", "ccc ddd", "bbb")


EXALPH = r"""\documentclass{article}
\usepackage[lazy]{linguexx}
%s
\begin{document}
\ex.\label{top}
\a.\label{one} First.
\b.\label{two} Second.
\a. Deeper.
\b. Deeper two.
\z.
\c. Third.

\end{document}"""


@pytest.mark.parametrize("setting", [r"\let\Exalph\roman", r"\let\Exalph=\roman",
                                     r"\renewcommand{\Exalph}{\roman}", r"\def\Exalph{\roman}"])
def test_exalph_counts_the_first_level(setting: str) -> None:
    r"""linguexx counts the first sub-example level with \Exalph, which a
    document may set to \roman.  Measured off its PDF: i., ii., the level
    below i., ii., then iii.; \ref gives (1i), \pref 1ii.  The converter
    lettered them a., b., c. regardless."""
    res = parse(EXALPH % setting)
    assert [(i.level, i.marker) for i in res.examples[0].items] == [
        (1, "i."), (1, "ii."), (2, "i."), (2, "ii."), (1, "iii.")]
    assert res.labels["one"] == (0, "i") and res.labels["two"] == (0, "ii")


def test_exalph_set_to_something_else_is_said() -> None:
    res = parse(EXALPH % r"\let\Exalph\fnsymbol")
    assert [i.marker for i in res.examples[0].items][:2] == ["a.", "b."]
    assert any(r"\Exalph is set to" in w for w in res.warnings)
