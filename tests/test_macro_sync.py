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

"""The Writer macro must agree with the converter about style names and
layout lengths, or a converted example and a macro-built one stop being
the same object.

Nothing here needs LibreOffice: it is a text comparison, so it runs in the
ordinary suite and catches the drift long before anyone renders anything.
The drift is not hypothetical — the macro was silently missing
``max_col_cm`` until this test was written.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from linguexx2odt import writermacro
from linguexx2odt.styles import MACRO_LENGTHS, MACRO_NAMES, Layout

ROOT = Path(__file__).resolve().parent.parent
SYNC = ROOT / "tools" / "sync_macro.py"


def test_the_macro_ships_with_the_package() -> None:
    """`pip install` must put the .bas on disk, not just the Python."""
    assert writermacro.path().is_file()
    assert "Sub GlossSelection" in writermacro.source()


def test_generated_block_matches_styles_py() -> None:
    """The whole check, exactly as tools/sync_macro.py performs it."""
    result = subprocess.run([sys.executable, str(SYNC)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_shared_name_is_declared() -> None:
    source = writermacro.source()
    for const, value in MACRO_NAMES.items():
        assert re.search(rf'Const {const}\s+As String = "{re.escape(value)}"', source), \
            f"{const} is missing or holds the wrong string"


def test_every_shared_length_is_declared_and_equal() -> None:
    source, layout = writermacro.source(), Layout()
    for const, attr in MACRO_LENGTHS.items():
        m = re.search(rf"Const {const}\s+As Double = ([\d.]+)", source)
        assert m, f"{const} is not declared in the macro"
        assert float(m.group(1)) == getattr(layout, attr), \
            f"{const} is {m.group(1)}, styles.py says {getattr(layout, attr)}"


def test_shared_lengths_are_actually_used() -> None:
    """A constant declared and never referenced is drift with a fig leaf —
    max_col_cm was absent from the macro's own width calculation, which is
    what made the two disagree in the first place."""
    source = writermacro.source()
    body = source.split("' --- END GENERATED", 1)[1]
    for const in MACRO_LENGTHS:
        assert const in body, f"{const} is declared but never used"
