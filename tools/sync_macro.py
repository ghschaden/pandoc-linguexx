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

"""Keep the Writer macro's constants identical to the converter's.

The macro is Basic and can import nothing, so the style names and layout
lengths exist twice.  This writes the second copy from the first.

    python3 tools/sync_macro.py            # check, exit 1 on drift
    python3 tools/sync_macro.py --write    # rewrite the generated block

``tests/test_macro_sync.py`` runs the check, so drift fails the suite
rather than surfacing as an example that is a millimetre out.
"""

from __future__ import annotations

import re
import sys
from dataclasses import fields
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from linguexx2odt.styles import (  # noqa: E402
    Layout, MACRO_LENGTHS, MACRO_NAMES, MACRO_NOT_SHARED,
)

MACRO = ROOT / "src" / "linguexx2odt" / "writermacro" / "LinguExx.bas"
BEGIN = "' --- BEGIN GENERATED — see tools/sync_macro.py; do not edit by hand"
END = "' --- END GENERATED"


def block() -> str:
    """The Basic declarations implied by styles.py."""
    layout = Layout()
    width = max(len(n) for n in list(MACRO_NAMES) + list(MACRO_LENGTHS))
    out = [
        BEGIN,
        "'",
        "' Style names and layout lengths shared with the converter, so that a",
        "' converted example and a macro-built one are the same object and",
        "' answer to the same styles.  Regenerate with:",
        "'",
        "'     python3 tools/sync_macro.py --write",
        "'",
    ]
    for name, value in MACRO_NAMES.items():
        out.append(f'Const {name:<{width}} As String = "{value}"')
    out.append("")
    out.append("' In centimetres, from linguexx2odt.styles.Layout.")
    for name, attr in MACRO_LENGTHS.items():
        out.append(f"Const {name:<{width}} As Double = {getattr(layout, attr)}")
    out.append("")
    out.append("' Deliberately not shared:")
    for attr, why in MACRO_NOT_SHARED.items():
        out.append(f"'   {attr} — {why}")
    out.append(END)
    return "\n".join(out)


def current(source: str) -> str:
    m = re.search(re.escape(BEGIN) + r".*?" + re.escape(END), source, re.S)
    if not m:
        sys.exit(
            f"{MACRO}: no generated block found.\n"
            f"Add these two lines around the Const declarations:\n"
            f"  {BEGIN}\n  {END}"
        )
    return m.group(0)


def main(argv: list[str]) -> int:
    source = MACRO.read_text(encoding="utf-8")
    have, want = current(source), block()
    if have == want:
        print(f"{MACRO.name}: in sync with styles.py")
        return 0
    if "--write" in argv:
        MACRO.write_text(source.replace(have, want), encoding="utf-8")
        print(f"{MACRO.name}: generated block rewritten")
        return 0
    print("the macro has drifted from src/linguexx2odt/styles.py\n")
    for line in _diff(have, want):
        print(line)
    print("\nrun: python3 tools/sync_macro.py --write")
    return 1


def _diff(have: str, want: str):
    import difflib
    return difflib.unified_diff(
        have.splitlines(), want.splitlines(),
        fromfile="LinguExx.bas", tofile="styles.py", lineterm="",
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
