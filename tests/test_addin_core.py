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
"""The JavaScript add-in core's contract with the converter, from the
Python side -- none of it needs Node, so it runs in the ordinary suite.

The core itself is tested by `node --test` (make js-test), against two
goldens this side owns:

* ``typed-examples.json``'s "parsed" section is the Writer macro's parse
  of every fixture, recorded and re-checked by tools/run_macro_test.py;
* ``typed-examples.plans.json`` is the converter's plan_table() on those
  parses, written by tools/addin_oracle.py and re-checked here.

So a change to the converter's geometry fails here until the golden is
regenerated -- and read -- and then fails the JavaScript until the core
follows.  constants.js is covered by test_macro_sync.py, which runs the same
sync tool that writes it.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "addin" / "core"
FIXTURES = ROOT / "tests" / "fixtures" / "typed-examples.json"


def test_every_fixture_has_the_macros_parse() -> None:
    """A case added without regenerating the parse golden tests nothing on
    the JavaScript side: its plan is never computed.  Say so here, where
    the fix -- LINGUEXX_UPDATE_GOLDEN=1 python3 tools/run_macro_test.py --
    is one line."""
    data = json.loads(FIXTURES.read_text(encoding="utf-8"))
    cases = {f"{group}/{name}"
             for group, cases in data.items()
             if not group.startswith("_") and group != "parsed"
             for name in cases}
    assert cases == set(data["parsed"]), (
        f"fixtures without a recorded macro parse: "
        f"{sorted(cases - set(data['parsed']))}; parses of no fixture: "
        f"{sorted(set(data['parsed']) - cases)}")


@pytest.mark.skipif(
    sys.version_info < (3, 12),
    reason="sum() of floats is compensated from Python 3.12 on, and the "
           "golden records that: an older sum() is a unit in the last place "
           "out, which the exact comparison would report as drift")
def test_the_plan_golden_is_the_converters() -> None:
    result = subprocess.run([sys.executable, str(ROOT / "tools" / "addin_oracle.py")],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


#: Words that only markup, or a host's API, would put in the core's code.
#: An ODF name has its local part straight after the colon -- `text:span`,
#: `table:table-cell` -- which is what tells it from an object key such as
#: `text: glossed ? ...`, the false positive this pattern first reported.
MARKUP = re.compile(
    r"<w:|\bw:(tbl|tc|tr|p|r|t)\b|\b(table|text|style|office):[a-z]|"
    r"\bApi\.|\bWord\.|\bOffice\.|insertOoxml|callCommand|\bAsc\.")


def _code(src: str) -> str:
    """JavaScript with its comments blanked out -- strings kept, because
    that is where markup would arrive.  Crude, and enough: the core has no
    regular expressions or strings containing comment openers."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(^|[^:\"'])//[^\n]*", r"\1", src)


def test_the_core_knows_no_markup() -> None:
    """addin/core is arithmetic and grammar.  The Word and OnlyOffice layers
    render its plan in their own vocabularies; the day OOXML or a builder
    call appears in the core, the other host inherits it -- the same
    invariant test_targets.py keeps for emit_base and measure."""
    files = sorted(CORE.glob("*.js"))
    assert files, "addin/core has no modules"
    offenders = []
    for path in files:
        for n, line in enumerate(_code(path.read_text(encoding="utf-8")).splitlines(), 1):
            if MARKUP.search(line):
                offenders.append(f"{path.name}:{n}: {line.strip()}")
    assert not offenders, "markup in the shared core:\n" + "\n".join(offenders)


def test_the_markup_check_can_fail() -> None:
    """The pattern above, shown to catch what it is for."""
    for bad in ['const x = "<w:tbl>";', "Word.run(ctx => 0)", "Api.CreateTable(1, 2)",
                'out += "<table:table-cell/>";', 'x = "text:span"']:
        assert MARKUP.search(_code(bad)), bad
    for fine in ["// renders as <w:tbl> in the Word layer",
                 'return { text: glossed ? "" : words };']:
        assert not MARKUP.search(_code(fine)), fine
