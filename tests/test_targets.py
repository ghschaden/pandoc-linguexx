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
"""The output-target seam.

Phase 1 of plan-docx.md, and all it is meant to do: one emitter reachable
by name, the geometry separated from the markup, and nothing else changed.
The rest of the suite is what proves the "nothing else" -- it reports the
same count as before the split, because the split was not supposed to do
anything.

What is worth testing here is the seam's own two claims: that the registry
resolves, and that the shared half stays shared. The second is the one that
rots quietly -- an emitter that reaches for `table:` in code meant to be
format-agnostic breaks nothing today and breaks the second target on the
day it is written.
"""

from __future__ import annotations

import re

import pytest

from linguexx2odt.emit_base import TARGETS, BaseEmitter, emitter_for
from linguexx2odt.emit_odt import Emitter


def test_each_target_resolves_to_its_emitter() -> None:
    from linguexx2odt.emit_docx import DocxEmitter

    assert isinstance(emitter_for("odt"), Emitter)
    assert isinstance(emitter_for("docx"), DocxEmitter)


def test_targets_write_different_raw_formats() -> None:
    """The format name is what tags a RawBlock, so the two must differ.

    It is also a ClassVar on purpose: annotated as a plain field it becomes
    part of the dataclass, every instance takes the base class's empty
    default, and every RawBlock goes out tagged "" — eighteen tests red and
    an .odt full of nothing.
    """
    seen = {name: cls.RAW_FORMAT for name, cls in TARGETS.items()}
    assert seen == {"odt": "opendocument", "docx": "openxml"}, seen
    assert all(v for v in seen.values()), "a target has no raw format"


def test_every_registered_target_is_an_emitter() -> None:
    assert TARGETS, "no targets registered; importing emit_odt should register one"
    for name, cls in TARGETS.items():
        assert issubclass(cls, BaseEmitter), f"{name} -> {cls} is not an emitter"


def test_an_unknown_target_says_what_it_knows() -> None:
    """The error names the targets that exist.

    A bare KeyError here would be read as a bug in the converter rather
    than as a typo in the argument.
    """
    with pytest.raises(ValueError, match="known targets: docx, odt"):
        emitter_for("rtf")


def test_the_shared_half_knows_nothing_about_odf() -> None:
    """emit_base and measure must not mention a markup vocabulary.

    This is the invariant the seam exists for. Geometry is arithmetic over
    centimetres; the moment a `table:` or a `w:` appears in it, the second
    target inherits the first one's markup and the split has quietly
    stopped being a split.
    """
    import ast

    from linguexx2odt import emit_base, measure

    for mod in (emit_base, measure):
        src = open(mod.__file__, encoding="utf-8").read()
        lines = src.splitlines()
        # Blank out comments AND docstrings.  Both modules discuss `table:`
        # and `w:` in prose on purpose -- explaining why they contain
        # neither is the whole point of their docstrings -- so a test that
        # reads prose as code fails on the very sentence that promises it
        # will not happen.  It did, on the first run.
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Module, ast.ClassDef,
                                     ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            doc = node.body[0] if node.body else None
            if (isinstance(doc, ast.Expr) and isinstance(doc.value, ast.Constant)
                    and isinstance(doc.value.value, str)):
                for i in range(doc.lineno - 1, doc.end_lineno):
                    lines[i] = ""
        code = "\n".join(
            line for line in lines if not line.lstrip().startswith("#")
        )
        # Anywhere in a code line, not just at the start of a literal: the
        # first version of this looked for '"table:' and sailed past
        # '"<table:table-cell/>"', which is exactly the leak it was for.
        leaks = re.findall(r"\b(?:table|text|office|style|fo):[a-zA-Z-]+"
                           r"|<w:[a-zA-Z]+", code)
        assert not leaks, (
            f"{mod.__name__} names markup in code: {sorted(set(leaks))[:5]} — "
            f"the format-agnostic half has learned a vocabulary"
        )
